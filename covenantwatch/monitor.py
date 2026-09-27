"""The daily monitoring run. Everything dated on or before `as_of` is processed; re-running is safe (alerts are keyed).

  1. financial covenants   tested each period against the borrower's numbers: green / amber / red, headroom,
                           next-period projection (amber if within 15% of the limit or trending to within 5% of it)
  2. fund policy triggers  the fund's own limits (D/E <= 2.0, interest cover >= 1.5) where no covenant covers the metric
  3. reporting covenants   each lender's deadline for monthly stock statements: late or missing
  4. data integrity        ratio reported in the compliance certificate vs recomputed from submitted financials
  5. events                classified to a covenant topic; alert if the borrower has that covenant and no consent is on record
An alert is raised when a status first turns amber or red (not every period it stays red), then notified once.

    python -m covenantwatch.monitor --as-of 2027-03-31
"""

import argparse
import json
from datetime import date

from covenantwatch.classify import classify
from covenantwatch.config import BORROWERS, DATA, EARLY_WARNING_HEADROOM, POLICY
from covenantwatch.db import audit, connect, raise_alert
from covenantwatch.notify import notify
from covenantwatch.taxonomy import TOPICS

METRIC_OF = {"FIN_DEBT_EQUITY": "debt_to_equity", "FIN_SECURITY_COVER": "security_cover", "FIN_FACR": "facr",
             "FIN_INTEREST_COVER": "interest_cover"}
STOCK_DEADLINES = {"madhur_steel": [("Bajaj Finance", 20, 431), ("RBL Bank", 25, 429)]}  # from the register (p. 431, 429)


def metrics(f) -> dict:
    debt = (f["current_borrowings"] or 0) + (f["noncurrent_borrowings"] or 0)
    out = {"debt_to_equity": debt / f["total_equity"] if f["total_equity"] else None,
           "interest_cover": (f["pbt"] + f["finance_costs"]) / f["finance_costs"] if f["finance_costs"] else None}
    if f["current_assets_charged"] and f["wc_outstanding"]:
        out["security_cover"] = f["current_assets_charged"] / f["wc_outstanding"]
    if f["collateral_value"] and f["facility_amount"]:
        out["facr"] = f["collateral_value"] / f["facility_amount"]
    return {k: round(v, 3) for k, v in out.items() if v is not None}


def status(actual: float, op: str, limit: float, projected: float | None) -> tuple[str, float]:
    if op == "<=":
        headroom = (limit - actual) / limit
        red = actual > limit
        near = projected is not None and projected >= 0.95 * limit
    else:
        headroom = (actual - limit) / limit
        red = actual < limit
        near = projected is not None and projected <= 1.05 * limit
    return ("red" if red else "amber" if headroom < EARLY_WARNING_HEADROOM or near else "green"), round(headroom * 100, 1)


def load(con, feed: dict, register: list[dict]) -> None:
    if not con.execute("SELECT 1 FROM covenants LIMIT 1").fetchone():
        con.executemany("INSERT INTO covenants (doc, topic, category, lender, description, operator, threshold, deadline, page, quote, status) "
                        "VALUES (:doc,:topic,:category,:lender,:description,:operator,:threshold,:deadline,:page,:quote,:status)", register)
    cols = ["doc", "period", "period_end", "source", "current_borrowings", "noncurrent_borrowings", "total_equity", "pbt", "finance_costs",
            "current_assets_charged", "wc_outstanding", "collateral_value", "facility_amount"]
    con.executemany(f"INSERT OR REPLACE INTO financials ({','.join(cols)}) VALUES ({','.join(':' + c for c in cols)})",
                    [{c: r.get(c) for c in cols} for r in feed["financials"]])
    con.executemany("INSERT OR REPLACE INTO certificates VALUES (:doc,:period,:metric,:reported,:submitted_on)", feed["certificates"])
    con.executemany("INSERT OR REPLACE INTO stock_statements VALUES (:doc,:month,:submitted_on)", feed["stock_statements"])
    for e in feed["events"]:
        con.execute("INSERT OR IGNORE INTO events (id, doc, date, text, consent_obtained) VALUES (?,?,?,?,?)",
                    (e["id"], e["doc"], e["date"], e["text"], None if e["consent_obtained"] is None else int(e["consent_obtained"])))


def financial_tests(con, as_of: str) -> list[str]:
    new = []
    for doc in BORROWERS:
        covs = {c["topic"]: c for c in con.execute("SELECT * FROM covenants WHERE doc=? AND category='financial' AND threshold IS NOT NULL", (doc,))}
        limits = [(METRIC_OF[t], "covenant", c["operator"], c["threshold"], f"p. {c['page']}: \"{c['quote'][:80]}\"") for t, c in covs.items() if t in METRIC_OF]
        covered = {m for m, *_ in limits}
        limits += [(m, "policy", op, v, "fund policy trigger") for m, (op, v) in POLICY.items() if m not in covered]
        rows = con.execute("SELECT * FROM financials WHERE doc=? AND period_end<=? ORDER BY period_end", (doc, as_of)).fetchall()
        history: dict[str, list[float]] = {}
        prev_status: dict[tuple, str] = {}
        for f in rows:
            m = metrics(f)
            for metric, kind, op, limit, evidence in limits:
                if metric not in m:
                    continue
                series = history.setdefault(metric, [])
                projected = m[metric] + (m[metric] - series[-1]) if series and f["source"] == "SIMULATED" else None
                st, headroom = status(m[metric], op, limit, projected)
                series.append(m[metric])
                con.execute("INSERT OR REPLACE INTO tests VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (doc, f["period"], metric, kind, m[metric], op, limit, st, headroom, projected))
                before = prev_status.get((metric, kind), "green")
                prev_status[(metric, kind)] = st
                worse = {"green": 0, "amber": 1, "red": 2}
                if worse[st] > worse[before]:
                    sev = ("high" if st == "red" else "medium") if kind == "covenant" else ("medium" if st == "red" else "low")
                    word = "BREACH" if st == "red" else "early warning"
                    proj = f"; trend projects {projected:.2f} next period" if projected is not None else ""
                    key = f"{doc}|{kind}|{metric}|{f['period']}"
                    if raise_alert(con, key, doc=doc, date=f["period_end"], severity=sev, kind=f"{kind}_{st}",
                                   title=f"{metric.replace('_', ' ')} {word} ({f['period']})",
                                   detail=f"{metric} = {m[metric]:.2f} vs limit {op} {limit} (headroom {headroom}%){proj}. Source data: {f['source']}.",
                                   evidence=evidence):
                        new.append(key)
    return new


def reporting(con, as_of: str) -> list[str]:
    new = []
    for doc, deadlines in STOCK_DEADLINES.items():
        for s in con.execute("SELECT * FROM stock_statements WHERE doc=?", (doc,)):
            y, mo = map(int, s["month"].split("-"))
            ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
            for lender, day, page in deadlines:
                due = f"{ny}-{nm:02d}-{day:02d}"
                if due > as_of and (s["submitted_on"] is None or s["submitted_on"] > as_of):
                    continue
                if s["submitted_on"] is None or s["submitted_on"] > as_of:
                    what, when = "not submitted", as_of
                elif s["submitted_on"] > due:
                    what, when = f"submitted {s['submitted_on']}, {(date.fromisoformat(s['submitted_on']) - date.fromisoformat(due)).days} day(s) late", s["submitted_on"]
                else:
                    continue
                key = f"{doc}|reporting|stock_statement|{s['month']}|{lender}"
                if raise_alert(con, key, doc=doc, date=when, severity="medium", kind="reporting",
                               title=f"Stock statement for {s['month']} {what.split(',')[0]} ({lender})",
                               detail=f"{lender} requires it by the {day}th of the following month (due {due}); {what}.",
                               evidence=f"register p. {page}"):
                    new.append(key)
    return new


def integrity(con, as_of: str) -> list[str]:
    new = []
    for c in con.execute("SELECT * FROM certificates WHERE submitted_on<=?", (as_of,)):
        f = con.execute("SELECT * FROM financials WHERE doc=? AND period=?", (c["doc"], c["period"])).fetchone()
        actual = metrics(f).get(c["metric"]) if f else None
        if actual is not None and abs(actual - c["reported"]) > 0.05 * max(actual, 0.01):
            key = f"{c['doc']}|integrity|{c['metric']}|{c['period']}"
            if raise_alert(con, key, doc=c["doc"], date=c["submitted_on"], severity="high", kind="integrity",
                           title=f"Compliance certificate does not match financials ({c['period']})",
                           detail=f"Reported {c['metric']} {c['reported']:.2f}; recomputed from submitted financials {actual:.2f}.",
                           evidence="certificate vs balance sheet"):
                new.append(key)
    return new


def events(con, as_of: str) -> list[str]:
    new = []
    for e in con.execute("SELECT * FROM events WHERE date<=?", (as_of,)).fetchall():
        topic, by = (e["topic"], e["classified_by"]) if e["topic"] else classify(e["text"])
        con.execute("UPDATE events SET topic=?, classified_by=? WHERE id=?", (topic, by, e["id"]))
        if topic == "NONE" or e["consent_obtained"] == 1:
            continue
        cov = con.execute("SELECT * FROM covenants WHERE doc=? AND topic=? LIMIT 1", (e["doc"], topic)).fetchone()
        cat = TOPICS[topic][0]
        if cov is None:
            sev, title, evidence = "low", f"Watch: {TOPICS[topic][1].lower()}", "no matching covenant in the register"
        elif cat == "default":
            sev, title, evidence = "high", f"Possible event of default: {TOPICS[topic][1].lower()}", f"p. {cov['page']}: \"{cov['quote'][:80]}\""
        else:
            sev, title, evidence = "high" if cat == "consent" and topic in ("CON_FRESH_BORROWING", "CON_FUND_DIVERSION_END_USE") else "medium", \
                f"Action needs lender consent, none on record: {TOPICS[topic][1].lower()}", f"p. {cov['page']}: \"{cov['quote'][:80]}\""
        key = f"{e['doc']}|event|{topic}|{e['id']}"
        if raise_alert(con, key, doc=e["doc"], date=e["date"], severity=sev, kind=f"event_{cat}", title=title,
                       detail=f"{e['date']}: {e['text']} (classified by {by} as {topic})", evidence=evidence):
            new.append(key)
    return new


def run(as_of: str, con=None, feed: dict | None = None, register: list[dict] | None = None, send: bool = True) -> list[str]:
    con = con or connect()
    feed = feed or json.loads((DATA / "feed_fy27_simulated.json").read_text(encoding="utf-8"))
    register = register if register is not None else json.loads((DATA / "register.json").read_text(encoding="utf-8"))
    load(con, feed, register)
    new = financial_tests(con, as_of) + reporting(con, as_of) + integrity(con, as_of) + events(con, as_of)
    audit(con, "run", {"as_of": as_of, "new_alerts": len(new)})
    con.commit()
    if send and new:
        notify(con, new)
    return new


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    a = ap.parse_args()
    for k in run(a.as_of):
        print(k)
