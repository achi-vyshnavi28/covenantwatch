"""SageMaker Ground Truth integration: manifests and config built from the 36 hand-labelled events, the
create_labeling_job request validated against the real AWS API model (botocore Stubber), S3 uploads on moto, and
scoring of an output manifest in Ground Truth's augmented format."""
import json

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

from covenantwatch import ground_truth as gt

JOB = "covenant-event-triage"
ROLE = "arn:aws:iam::123456789012:role/GroundTruthRole"
TEAM = "arn:aws:sagemaker:us-east-1:123456789012:workteam/private-crowd/covenant-team"


@pytest.fixture
def events():
    return gt.load_events()


def test_input_manifest_has_one_line_per_real_event(events):
    lines = gt.input_manifest(events).splitlines()
    assert len(lines) == 36
    first = json.loads(lines[0])
    assert first["event-id"] == "E01" and "HDFC Bank" in first["source"]


def test_label_categories_cover_every_gold_topic_and_none(events):
    cfg = gt.label_config(events)
    labels = [l["label"] for l in cfg["labels"]]
    assert set(labels) == {e["topic"] for e in events} and labels[-1] == "NONE" and len(labels) == len(set(labels))
    assert "Credit rating downgrade" in cfg["instructions"]["fullInstruction"]


def test_worker_template_is_a_crowd_classifier_over_the_same_categories(events):
    html = gt.ui_template(events)
    assert "<crowd-classifier" in html and "{{ task.input.taskObject }}" in html
    cats = json.loads(html.split("categories='")[1].split("'")[0])
    assert cats == [l["label"] for l in gt.label_config(events)["labels"]]


def test_labeling_job_request_is_valid_for_the_aws_api():
    req = gt.job_request(JOB, "cw-labels", ROLE, TEAM)
    assert req["HumanTaskConfig"]["NumberOfHumanWorkersPerDataObject"] == 3
    client = boto3.client("sagemaker", region_name="us-east-1", aws_access_key_id="t", aws_secret_access_key="t")
    with Stubber(client) as stub:  # Stubber rejects any parameter that does not match the CreateLabelingJob model
        stub.add_response("create_labeling_job", {"LabelingJobArn": f"arn:aws:sagemaker:us-east-1:123456789012:labeling-job/{JOB}"}, req)
        assert client.create_labeling_job(**req)["LabelingJobArn"].endswith(JOB)
    with pytest.raises(ValueError):
        gt.job_request(JOB, "cw-labels", ROLE, TEAM, region="eu-west-9")


def test_prepare_uploads_encrypted_job_files_to_s3(events, monkeypatch):
    for k, v in {"AWS_DEFAULT_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": "t", "AWS_SECRET_ACCESS_KEY": "t"}.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="cw-labels")
        uris = gt.prepare("cw-labels", JOB, s3, events)
        assert set(uris) == {"input.manifest", "label-categories.json", "template.liquid"}
        obj = s3.get_object(Bucket="cw-labels", Key=f"ground-truth/{JOB}/input.manifest")
        assert obj["ServerSideEncryption"] == "AES256" and obj["Body"].read().decode().count("\n") == 36


def test_output_manifest_is_scored_against_gold_and_unsure_items_go_to_review(events):
    """Format check with a constructed output manifest: annotators match gold except one decoy, plus one low-confidence item."""
    decoy = next(e["id"] for e in events if e["topic"] == "NONE")
    lines = []
    for e in events:
        label = "CON_FRESH_BORROWING" if e["id"] == decoy else e["topic"]
        conf = 0.52 if e["id"] == "E05" else 0.94
        lines.append(json.dumps({"source": e["text"], "event-id": e["id"], JOB: 0,
                                 f"{JOB}-metadata": {"class-name": label, "confidence": conf, "human-annotated": "yes",
                                                     "type": "groundtruth/text-classification"}}))
    s = gt.score(events, gt.read_output(lines, JOB))
    assert s["events"] == 36 and s["agreement"] == round(35 / 36, 3)
    assert s["false_alerts"] == 1 and s["missed_events"] == 0
    assert s["top_disagreements"] == [{"gold": "NONE", "annotators": "CON_FRESH_BORROWING", "count": 1}]
    assert "E05" in s["review_queue"] and len(s["review_queue"]) == 2
