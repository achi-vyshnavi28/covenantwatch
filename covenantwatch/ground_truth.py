"""Amazon SageMaker Ground Truth for the event-triage labels: send news events to human annotators and score them.

    python -m covenantwatch.ground_truth prepare --bucket <bucket>          # manifests + label config + template to S3
    python -m covenantwatch.ground_truth launch  --bucket <bucket> --role <arn> --workteam <arn>
    python -m covenantwatch.ground_truth score   --output <output.manifest>   # agreement with evals/events.json

The job is single-label text classification with the covenant taxonomy as categories, three annotators per event and
Ground Truth's built-in consensus. Returned labels are scored against the hand-made gold set, and events where the
annotators were unsure (low consensus confidence) or disagree with gold are listed for review, which is how the label
taxonomy itself gets audited.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from covenantwatch.taxonomy import TOPICS

EVENTS = Path(__file__).resolve().parents[1] / "evals" / "events.json"
NONE = "NONE"  # routine news that touches no covenant (the decoys)
REVIEW_BELOW = 0.70  # consensus confidence under this goes to a second-pass review

# AWS-managed pre-annotation and consolidation Lambdas for text classification (us-east-1).
BUILT_IN = {"us-east-1": ("arn:aws:lambda:us-east-1:432418664414:function:PRE-TextMultiClass",
                          "arn:aws:lambda:us-east-1:432418664414:function:ACS-TextMultiClass")}


def load_events(path=EVENTS) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def labels_in_use(events) -> list[str]:
    """Categories for the job: the taxonomy topics that occur in the events, plus NONE for routine news."""
    used = {e["topic"] for e in events}
    return [t for t in TOPICS if t in used] + [NONE]


def input_manifest(events) -> str:
    """JSON Lines input manifest; 'source' carries the text inline, so no per-object files are needed."""
    return "\n".join(json.dumps({"source": e["text"], "event-id": e["id"]}, ensure_ascii=False) for e in events) + "\n"


def label_config(events) -> dict:
    return {"document-version": "2018-11-28",
            "labels": [{"label": t} for t in labels_in_use(events)],
            "instructions": {"shortInstruction": "Pick the one loan covenant this news event could trigger, or NONE "
                                                 "if it is routine business news.",
                             "fullInstruction": "\n".join(f"{t}: {TOPICS[t][1]}" for t in labels_in_use(events)
                                                          if t in TOPICS)}}


def ui_template(events) -> str:
    """Liquid template rendered for each annotator (crowd-classifier from the Crowd HTML Elements)."""
    cats = json.dumps(labels_in_use(events))
    guide = "".join(f"<li><b>{t}</b>: {TOPICS[t][1]}</li>" for t in labels_in_use(events) if t in TOPICS)
    return f"""<script src="https://assets.crowd.aws/crowd-html-elements.js"></script>
<crowd-form>
  <crowd-classifier name="crowd-classifier" categories='{cats}' header="Which loan covenant could this event trigger?">
    <classification-target>{{{{ task.input.taskObject }}}}</classification-target>
    <full-instructions header="Covenant topics"><ul>{guide}<li><b>{NONE}</b>: routine news, no covenant</li></ul></full-instructions>
    <short-instructions>Choose one topic. Choose {NONE} for routine business news such as product launches.</short-instructions>
  </crowd-classifier>
</crowd-form>
"""


def job_request(job_name, bucket, role_arn, workteam_arn, region="us-east-1", annotators=3) -> dict:
    """Parameters for sagemaker.create_labeling_job (checked against the AWS API model in the tests)."""
    if region not in BUILT_IN:
        raise ValueError(f"built-in text-classification Lambdas are configured for {sorted(BUILT_IN)} only")
    pre, acs = BUILT_IN[region]
    s3 = f"s3://{bucket}/ground-truth/{job_name}"
    return {
        "LabelingJobName": job_name,
        "LabelAttributeName": job_name,
        "InputConfig": {"DataSource": {"S3DataSource": {"ManifestS3Uri": f"{s3}/input.manifest"}},
                        "DataAttributes": {"ContentClassifiers": ["FreeOfPersonallyIdentifiableInformation"]}},
        "OutputConfig": {"S3OutputPath": f"{s3}/output/"},
        "RoleArn": role_arn,
        "LabelCategoryConfigS3Uri": f"{s3}/label-categories.json",
        "StoppingConditions": {"MaxPercentageOfInputDatasetLabeled": 100},
        "HumanTaskConfig": {
            "WorkteamArn": workteam_arn,
            "UiConfig": {"UiTemplateS3Uri": f"{s3}/template.liquid"},
            "PreHumanTaskLambdaArn": pre,
            "TaskTitle": "Classify loan-covenant news events",
            "TaskDescription": "Pick the covenant topic a news event about a borrower could trigger",
            "TaskKeywords": ["text", "classification", "finance"],
            "NumberOfHumanWorkersPerDataObject": annotators,
            "TaskTimeLimitInSeconds": 300,
            "TaskAvailabilityLifetimeInSeconds": 3 * 24 * 3600,
            "MaxConcurrentTaskCount": 100,
            "AnnotationConsolidationConfig": {"AnnotationConsolidationLambdaArn": acs},
        },
        "Tags": [{"Key": "project", "Value": "covenantwatch"}],
    }


def prepare(bucket, job_name, s3=None, events=None) -> dict:
    """Upload the input manifest, label categories and worker template to S3."""
    import boto3

    s3 = s3 or boto3.client("s3")
    events = events or load_events()
    prefix = f"ground-truth/{job_name}"
    files = {"input.manifest": input_manifest(events), "label-categories.json": json.dumps(label_config(events), indent=1),
             "template.liquid": ui_template(events)}
    for name, body in files.items():
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{name}", Body=body.encode("utf-8"), ServerSideEncryption="AES256")
    return {name: f"s3://{bucket}/{prefix}/{name}" for name in files}


def read_output(manifest_lines, job_name) -> dict:
    """Parse Ground Truth's augmented output manifest -> {event id: {label, confidence, human}}."""
    out = {}
    for line in manifest_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        meta = row.get(f"{job_name}-metadata", {})
        out[row["event-id"]] = {"label": meta.get("class-name"), "confidence": float(meta.get("confidence", 0)),
                                "human": meta.get("human-annotated") == "yes"}
    return out


def score(gold_events, labelled: dict) -> dict:
    """Agreement of annotator labels with the gold set, per-topic disagreements and the review queue."""
    gold = {e["id"]: e["topic"] for e in gold_events}
    common = [i for i in gold if i in labelled]
    agree = [i for i in common if labelled[i]["label"] == gold[i]]
    disagreements = Counter((gold[i], labelled[i]["label"]) for i in common if i not in agree)
    review = sorted(i for i in common if i not in agree or labelled[i]["confidence"] < REVIEW_BELOW)
    return {"events": len(common), "agreement": round(len(agree) / len(common), 3) if common else None,
            "false_alerts": sum(1 for i in common if gold[i] == NONE and labelled[i]["label"] != NONE),
            "missed_events": sum(1 for i in common if gold[i] != NONE and labelled[i]["label"] == NONE),
            "top_disagreements": [{"gold": g, "annotators": a, "count": n} for (g, a), n in disagreements.most_common(5)],
            "review_queue": review}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "launch", "score"])
    ap.add_argument("--bucket"), ap.add_argument("--role"), ap.add_argument("--workteam"), ap.add_argument("--output")
    ap.add_argument("--job", default="covenant-event-triage")
    a = ap.parse_args()
    if a.cmd == "prepare":
        print(json.dumps(prepare(a.bucket, a.job), indent=1))
    elif a.cmd == "launch":
        import boto3

        print(boto3.client("sagemaker").create_labeling_job(**job_request(a.job, a.bucket, a.role, a.workteam))["LabelingJobArn"])
    else:
        print(json.dumps(score(load_events(), read_output(Path(a.output).read_text(encoding="utf-8").splitlines(), a.job)), indent=1))
