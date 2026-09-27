"""Which covenant does a news item, lender notice or board decision touch?

Two classifiers, compared on 36 labelled events (evals/events.json):
  keyword   the taxonomy's keyword lists; free, instant, transparent
  llm       the model reads the event and the taxonomy; handles paraphrase ("block deal", "foreclosed")
The monitor uses the LLM, and falls back to keywords if the model is unavailable.

    python -m covenantwatch.classify
"""

import json
import sys

from pydantic import BaseModel

from covenantwatch.config import DEFAULT_MODEL, REPORTS, ROOT
from covenantwatch.llm import call
from covenantwatch.taxonomy import NONE, TOPICS


def keyword(text: str) -> str:
    t = text.lower()
    best, hits = NONE, 0
    for topic, (_, _, words) in TOPICS.items():
        n = sum(w in t for w in words)
        if n > hits:
            best, hits = topic, n
    return best


class Label(BaseModel):
    topic: str
    confidence: float = 0.5
    reason: str = ""


SYSTEM = """You monitor loan covenants for a private-credit fund. Classify the event into the ONE covenant topic it
could trigger, or NONE if it touches no covenant (routine business news, on-time payments, product launches).
Topics (id: meaning):
{taxonomy}
Return JSON: {{"topic": "<id or NONE>", "confidence": 0-1, "reason": "one sentence"}}"""


def llm(text: str, model: str = DEFAULT_MODEL) -> Label:
    taxonomy = "\n".join(f"{k}: {v[1]}" for k, v in TOPICS.items() if v[0] != "financial" and not k.startswith("REP_"))
    label, _ = call(model, SYSTEM.format(taxonomy=taxonomy), f"Event: {text}", Label)
    if label.topic not in TOPICS:
        label.topic = NONE
    return label


def classify(text: str, model: str = DEFAULT_MODEL) -> tuple[str, str]:
    try:
        return llm(text, model).topic, "llm"
    except Exception:  # model down or quota exhausted: degrade to rules, never stop monitoring
        return keyword(text), "keyword"


def evaluate(model: str = DEFAULT_MODEL) -> dict:
    events = json.loads((ROOT / "evals" / "events.json").read_text(encoding="utf-8"))
    out = {}
    for name, fn in (("keyword", keyword), ("llm", lambda t: llm(t, model).topic)):
        preds = [(e, fn(e["text"])) for e in events]
        correct = sum(p == e["topic"] for e, p in preds)
        flagged = [(e, p) for e, p in preds if p != NONE]
        real = [e for e in events if e["topic"] != NONE]
        out[name] = {
            "accuracy": round(correct / len(events), 3),
            "alert_precision": round(sum(p == e["topic"] for e, p in flagged) / len(flagged), 3) if flagged else None,
            "alert_recall": round(sum(p == e["topic"] for e, p in preds if e["topic"] != NONE) / len(real), 3),
            "false_alerts_on_noise": sum(p != NONE for e, p in preds if e["topic"] == NONE),
            "errors": [f"{e['id']}: expected {e['topic']}, got {p}" for e, p in preds if p != e["topic"]],
        }
    return out


if __name__ == "__main__":
    res = evaluate(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "event_classification.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    for k, v in res.items():
        print(k, {kk: vv for kk, vv in v.items() if kk != "errors"})
        for e in v["errors"]:
            print("   ", e)
