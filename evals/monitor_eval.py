"""Replay FY2027 week by week on a fresh database and compare alerts with the planted problems.

Reports: planted problems caught, false alerts, alert volume, and how many days after the triggering fact each alert
appeared (weekly runs, so at most 7 days is expected).

    python -m evals.monitor_eval
"""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from covenantwatch.config import DATA, REPORTS, ROOT
from covenantwatch.db import connect
from covenantwatch.monitor import run
from covenantwatch.simulate import build


def main() -> dict:
    feed = build()
    register = json.loads((DATA / "register.json").read_text(encoding="utf-8"))
    expected = set(json.loads((ROOT / "evals" / "expected_alerts.json").read_text(encoding="utf-8"))["expected"])
    first_seen = {}
    with tempfile.TemporaryDirectory() as tmp:
        con = connect(Path(tmp) / "eval.sqlite3")
        d = date(2026, 4, 1)
        while d <= date(2027, 4, 30):
            for key in run(d.isoformat(), con=con, feed=feed, register=register, send=False):
                first_seen[key] = d.isoformat()
            d += timedelta(days=7)
        alerts = {r["key"]: dict(r) for r in con.execute("SELECT * FROM alerts")}
        rerun = run("2027-04-30", con=con, feed=feed, register=register, send=False)
        con.close()
    got = set(alerts)
    delays = [(date.fromisoformat(first_seen[k]) - date.fromisoformat(alerts[k]["date"])).days for k in got & expected
              if alerts[k]["date"] >= "2026-04-01"]
    res = {"planted_problems_caught": f"{len(got & expected)}/{len(expected)}", "missed": sorted(expected - got),
           "false_alerts": sorted(got - expected), "total_alerts": len(got),
           "max_days_to_alert": max(delays) if delays else None, "rerun_new_alerts": len(rerun),
           "alerts": [{k: v for k, v in alerts[k].items() if k in ("key", "date", "severity", "title", "detail", "evidence")} for k in sorted(got)]}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "monitor_eval.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main()
    print({k: v for k, v in r.items() if k != "alerts"})
    for a in r["alerts"]:
        print(f"  [{a['severity']:6s}] {a['date']} {a['key']}")
