"""HTTP API for the fund's systems (portfolio tools, Slack bots, n8n).

    uvicorn covenantwatch.api:app --port 8901
    GET  /portfolio                   latest status per borrower and metric (SQL view v_latest)
    GET  /alerts?status=open          alerts, most severe first
    POST /alerts/{key}/feedback       analyst verdict: "confirmed" | "false_positive" | "resolved" (+ comment)
    GET  /register/{doc}              covenant register with page citations
    POST /register/{doc}/confirm      analyst confirms extracted covenants (onboarding sign-off)
    POST /events                      new event (news, lender notice) -> classified and checked immediately
    POST /run?as_of=YYYY-MM-DD        run the daily monitor (idempotent)
"""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from covenantwatch.config import BORROWERS
from covenantwatch.db import audit, connect
from covenantwatch.monitor import run

app = FastAPI(title="CovenantWatch", description="Covenant monitoring for private-credit portfolios")
SEVERITY = "CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"


class FeedbackIn(BaseModel):
    verdict: Literal["confirmed", "false_positive", "resolved"]
    comment: str = ""


class EventIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    doc: str
    date: date
    text: str = Field(min_length=10, max_length=1000)
    consent_obtained: bool | None = None


def _doc(doc: str) -> None:
    if doc not in BORROWERS:
        raise HTTPException(404, f"unknown borrower '{doc}'")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "borrowers": len(BORROWERS)}


@app.get("/portfolio")
def portfolio() -> list[dict]:
    con = connect()
    return [dict(r) for r in con.execute("SELECT doc, metric, kind, period, actual, operator, limit_value, status, headroom_pct "
                                         "FROM v_latest ORDER BY doc, kind, metric")]


@app.get("/alerts")
def alerts(status: str = "open", doc: str | None = None) -> list[dict]:
    con = connect()
    q, args = f"SELECT * FROM alerts WHERE status=?", [status]
    if doc:
        q, args = q + " AND doc=?", args + [doc]
    return [dict(r) for r in con.execute(q + f" ORDER BY {SEVERITY}, date DESC", args)]


@app.post("/alerts/{key:path}/feedback")
def feedback(key: str, body: FeedbackIn) -> dict:
    con = connect()
    if not con.execute("SELECT 1 FROM alerts WHERE key=?", (key,)).fetchone():
        raise HTTPException(404, "unknown alert")
    new_status = {"confirmed": "open", "false_positive": "dismissed", "resolved": "resolved"}[body.verdict]
    con.execute("UPDATE alerts SET status=? WHERE key=?", (new_status, key))
    con.execute("INSERT INTO feedback VALUES (?,?,?,?)", (key, body.verdict, body.comment, datetime.now(timezone.utc).isoformat()))
    audit(con, "feedback", {"key": key, "verdict": body.verdict})
    con.commit()
    return {"key": key, "status": new_status}


@app.get("/register/{doc}")
def register(doc: str) -> list[dict]:
    _doc(doc)
    return [dict(r) for r in connect().execute("SELECT * FROM covenants WHERE doc=? ORDER BY category, topic", (doc,))]


@app.post("/register/{doc}/confirm")
def confirm(doc: str) -> dict:
    _doc(doc)
    con = connect()
    n = con.execute("UPDATE covenants SET status='confirmed' WHERE doc=? AND status='extracted'", (doc,)).rowcount
    audit(con, "register_confirmed", {"doc": doc, "covenants": n})
    con.commit()
    return {"doc": doc, "confirmed": n}


@app.post("/events")
def add_event(body: EventIn) -> dict:
    _doc(body.doc)
    con = connect()
    con.execute("INSERT OR IGNORE INTO events (id, doc, date, text, consent_obtained) VALUES (?,?,?,?,?)",
                (body.id, body.doc, body.date.isoformat(), body.text, None if body.consent_obtained is None else int(body.consent_obtained)))
    con.commit()
    new = run(body.date.isoformat(), con=con)
    return {"new_alerts": [dict(r) for r in con.execute(f"SELECT * FROM alerts WHERE key IN ({','.join('?' * len(new))})", new)] if new else []}


@app.post("/run")
def run_now(as_of: date | None = None) -> dict:
    new = run((as_of or date.today()).isoformat())
    return {"as_of": str(as_of or date.today()), "new_alerts": new}
