"""SQLite store. Alerts are keyed so a re-run never duplicates one (idempotent daily jobs)."""

import json
import sqlite3
from datetime import datetime, timezone

from covenantwatch.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS covenants (
  id INTEGER PRIMARY KEY, doc TEXT, topic TEXT, category TEXT, lender TEXT, description TEXT,
  operator TEXT, threshold REAL, deadline TEXT, page INTEGER, quote TEXT, status TEXT DEFAULT 'extracted');
CREATE TABLE IF NOT EXISTS financials (
  doc TEXT, period TEXT, period_end TEXT, source TEXT,
  current_borrowings REAL, noncurrent_borrowings REAL, total_equity REAL, pbt REAL, finance_costs REAL,
  current_assets_charged REAL, wc_outstanding REAL, collateral_value REAL, facility_amount REAL,
  PRIMARY KEY (doc, period));
CREATE TABLE IF NOT EXISTS certificates (
  doc TEXT, period TEXT, metric TEXT, reported REAL, submitted_on TEXT, PRIMARY KEY (doc, period, metric));
CREATE TABLE IF NOT EXISTS stock_statements (
  doc TEXT, month TEXT, submitted_on TEXT, PRIMARY KEY (doc, month));
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, doc TEXT, date TEXT, text TEXT, consent_obtained INTEGER, topic TEXT, classified_by TEXT);
CREATE TABLE IF NOT EXISTS tests (
  doc TEXT, period TEXT, metric TEXT, kind TEXT, actual REAL, operator TEXT, limit_value REAL,
  status TEXT, headroom_pct REAL, projected_next REAL, PRIMARY KEY (doc, period, metric, kind));
CREATE TABLE IF NOT EXISTS alerts (
  key TEXT PRIMARY KEY, doc TEXT, date TEXT, severity TEXT, kind TEXT, title TEXT, detail TEXT,
  evidence TEXT, status TEXT DEFAULT 'open', notified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback (alert_key TEXT, verdict TEXT, comment TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS audit (at TEXT, action TEXT, detail TEXT);

-- latest test per borrower and metric (portfolio heatmap)
CREATE VIEW IF NOT EXISTS v_latest AS
SELECT * FROM (
  SELECT t.*, ROW_NUMBER() OVER (PARTITION BY doc, metric, kind ORDER BY period DESC) AS rn FROM tests t
) WHERE rn = 1;

-- headroom trend with change vs previous period
CREATE VIEW IF NOT EXISTS v_trend AS
SELECT doc, metric, kind, period, actual, limit_value, status, headroom_pct,
       actual - LAG(actual) OVER (PARTITION BY doc, metric, kind ORDER BY period) AS change_vs_prev
FROM tests;

-- open alerts by borrower and severity
CREATE VIEW IF NOT EXISTS v_open_alerts AS
SELECT doc, severity, COUNT(*) AS n FROM alerts WHERE status = 'open' GROUP BY doc, severity;
"""


def connect(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or DB_PATH))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def audit(con: sqlite3.Connection, action: str, detail: dict | str) -> None:
    con.execute("INSERT INTO audit VALUES (?, ?, ?)", (datetime.now(timezone.utc).isoformat(), action,
                                                        detail if isinstance(detail, str) else json.dumps(detail)))


def raise_alert(con: sqlite3.Connection, key: str, **a) -> bool:
    """Insert once. Returns True only for a new alert (so notifications fire once)."""
    cur = con.execute("INSERT OR IGNORE INTO alerts (key, doc, date, severity, kind, title, detail, evidence) VALUES (?,?,?,?,?,?,?,?)",
                      (key, a["doc"], a["date"], a["severity"], a["kind"], a["title"], a["detail"], a.get("evidence", "")))
    if cur.rowcount:
        audit(con, "alert_raised", {"key": key, "severity": a["severity"]})
    return bool(cur.rowcount)
