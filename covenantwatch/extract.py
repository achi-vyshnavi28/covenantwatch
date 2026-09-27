"""Onboarding step 1: turn the loan terms in a filing into a covenant register.

The LLM reads the borrower's "Financial Indebtedness" pages and returns every covenant mapped to the taxonomy,
with the page and a verbatim quote. A covenant is kept only if its quote is really on that page; everything else
is dropped and logged. The register then goes to an analyst to confirm (status "extracted" -> "confirmed").

    python -m covenantwatch.extract            # all borrowers, prints precision / recall against the hand-labelled register
"""

import json
import re
import sys

from pydantic import BaseModel, field_validator

from covenantwatch.config import BORROWERS, DEFAULT_MODEL, FILINGS, REPORTS, ROOT
from covenantwatch.llm import call
from covenantwatch.taxonomy import TOPICS


class Covenant(BaseModel):
    topic: str
    lender: str | None = None
    description: str = ""
    operator: str | None = None  # "<=" or ">=" for financial covenants
    threshold: float | None = None
    deadline: str | None = None  # e.g. "20th of following month", "within 30 days of execution"
    page: int
    quote: str

    @field_validator("threshold", mode="before")
    @classmethod
    def _t(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        m = re.search(r"\d+(\.\d+)?", str(v))
        return float(m.group(0)) if m else None


class Register(BaseModel):
    covenants: list[Covenant]


SYSTEM = """You are onboarding a borrower into a private-credit covenant monitoring system.
From the loan-terms pages of an Indian DRHP, list EVERY covenant, condition or event of default, each mapped to exactly
one topic from this taxonomy (id: meaning):
{taxonomy}
Rules:
- Include a covenant only if the text states it. If a clause fits no topic, skip it.
- page: the number in the [page N] header above the text you used. Ignore page numbers printed inside the text itself.
  quote: a short verbatim span copied exactly from that page.
- For financial covenants give operator ("<=" for a maximum, ">=" for a minimum) and threshold as a number (e.g. 3.33 for "3.33:1", 1.33 for "1.33X").
- For reporting covenants give the deadline in words.
- The same topic may appear for several lenders; list each lender's version separately.
Return JSON: {{"covenants": [{{"topic", "lender", "description", "operator", "threshold", "deadline", "page", "quote"}}]}}"""


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("’", "'").replace("“", '"').replace("”", '"')).lower()


def pages(doc: str) -> dict[int, str]:
    return {int(k): v for k, v in json.loads((FILINGS / f"{doc}.json").read_text(encoding="utf-8"))["covenant_pages"].items()}


def extract(doc: str, model: str = DEFAULT_MODEL) -> tuple[list[dict], list[dict], dict]:
    text = pages(doc)
    taxonomy = "\n".join(f"{k}: {v[1]}" for k, v in TOPICS.items())
    body = "\n\n".join(f"[page {p}]\n{re.sub(r'[ \t]+', ' ', t)}" for p, t in text.items())
    reg, meta = call(model, SYSTEM.format(taxonomy=taxonomy), f"Borrower: {BORROWERS[doc]['name']}\n\n{body}", Register)
    kept, dropped = [], []
    for c in reg.covenants:
        reason, note = None, None
        if c.page not in text or squash(c.quote) not in squash(text[c.page]):
            # DRHPs print their own page numbers (PDF page 441 shows "436"); models often cite the printed one.
            # If the quote exists on exactly one page, cite that page instead; the quote itself is still verified.
            where = [p for p, t in text.items() if squash(c.quote) and squash(c.quote) in squash(t)]
            if len(where) == 1:
                note, c.page = f"page corrected {c.page}->{where[0]}", where[0]
        if c.topic not in TOPICS:
            reason = f"unknown topic {c.topic}"
        elif c.page not in text or squash(c.quote) not in squash(text[c.page]):
            reason = "quote not found on the cited page"
        elif TOPICS[c.topic][0] == "financial" and c.threshold is not None and \
                not any(abs(float(n) - c.threshold) < 1e-6 for n in re.findall(r"\d+\.?\d*", c.quote)):
            reason = "threshold not in the quote"
        (dropped if reason else kept).append({**c.model_dump(), "doc": doc, **({"reason": reason} if reason else {}),
                                              **({"note": note} if note else {}),
                                              "category": TOPICS.get(c.topic, ("?",))[0], "status": "extracted"})
    return kept, dropped, meta


def score(doc: str, kept: list[dict]) -> dict:
    gold = json.loads((ROOT / "evals" / "gold_register.json").read_text(encoding="utf-8"))[doc]
    want, got = set(gold["topics"]), {c["topic"] for c in kept}
    fin = {}
    for topic, g in gold["financial"].items():
        hits = [c for c in kept if c["topic"] == topic]
        fin[topic] = any(c["threshold"] == g["threshold"] and c["operator"] == g["operator"] for c in hits)
    return {"precision": round(len(want & got) / len(got), 3) if got else None, "recall": round(len(want & got) / len(want), 3),
            "missed": sorted(want - got), "extra": sorted(got - want), "financial_thresholds_exact": fin}


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    report, register = {}, []
    for doc in BORROWERS:
        kept, dropped, meta = extract(doc, model)
        register += kept
        report[doc] = {**score(doc, kept), "covenants_kept": len(kept), "dropped_unverified": len(dropped),
                       "pages_corrected": sum("note" in c for c in kept),
                       "dropped_examples": [f"{d['topic']} p.{d['page']}: {d['reason']}" for d in dropped[:5]],
                       "latency_s": meta["latency_s"], "cost_usd": meta["cost_usd"]}
        print(doc, json.dumps(report[doc]), flush=True)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"extraction_{model}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "data" / "register.json").write_text(json.dumps(register, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
