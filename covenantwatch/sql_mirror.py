"""Relational store for reporting: syncs covenant tests and alerts into PostgreSQL or MySQL (SQLAlchemy Core).

The daily job runs on SQLite; a fund's BI tools, finance team and other services read from a shared PostgreSQL or
MySQL database. The sync is an idempotent upsert using each database's native form (ON CONFLICT on PostgreSQL and
SQLite, ON DUPLICATE KEY UPDATE on MySQL), so it can run after every monitor run. The same window-function views as the
local store (latest status per borrower with ROW_NUMBER, change versus last period with LAG) are created on the target.

    python -m covenantwatch.sql_mirror --url postgresql+psycopg://user:pass@host/db
"""
import argparse
import os

from sqlalchemy import Column, Float, Index, MetaData, String, Table, Text, create_engine, select, text
from sqlalchemy.dialects import mysql, postgresql, sqlite

metadata = MetaData()
tests = Table(
    "cw_tests", metadata,
    Column("doc", String(60), primary_key=True), Column("period", String(20), primary_key=True),
    Column("metric", String(40), primary_key=True), Column("kind", String(20), primary_key=True),
    Column("actual", Float), Column("operator", String(4)), Column("limit_value", Float),
    Column("status", String(10)), Column("headroom_pct", Float), Column("projected_next", Float),
    Index("ix_cw_tests_status", "status"),
)
alerts = Table(
    "cw_alerts", metadata,
    Column("alert_key", String(200), primary_key=True), Column("doc", String(60), index=True), Column("date", String(20)),
    Column("severity", String(10)), Column("kind", String(40)), Column("title", String(300)), Column("detail", Text),
    Column("evidence", Text), Column("status", String(20)),
    Index("ix_cw_alerts_open", "status", "severity"),
)

VIEWS = {
    "cw_v_latest": """CREATE VIEW cw_v_latest AS
        SELECT doc, period, metric, kind, actual, operator, limit_value, status, headroom_pct FROM (
          SELECT t.*, ROW_NUMBER() OVER (PARTITION BY doc, metric, kind ORDER BY period DESC) AS rn FROM cw_tests t
        ) ranked WHERE rn = 1""",
    "cw_v_trend": """CREATE VIEW cw_v_trend AS
        SELECT doc, metric, kind, period, actual, status, headroom_pct,
               actual - LAG(actual) OVER (PARTITION BY doc, metric, kind ORDER BY period) AS change_vs_prev
        FROM cw_tests""",
}


def engine_for(url: str | None = None):
    return create_engine(url or os.environ["COVENANTWATCH_SQL_URL"], future=True)


def create_schema(engine):
    metadata.create_all(engine)
    with engine.begin() as c:
        for name, ddl in VIEWS.items():
            c.execute(text(f"DROP VIEW IF EXISTS {name}"))
            c.execute(text(ddl))


def _upsert(engine, table, rows: list[dict], keys: list[str]):
    if not rows:
        return
    name = engine.dialect.name
    if name == "postgresql":
        stmt = postgresql.insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(index_elements=keys,
                                          set_={c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys})
    elif name == "mysql":
        stmt = mysql.insert(table).values(rows)
        stmt = stmt.on_duplicate_key_update({c.name: stmt.inserted[c.name] for c in table.columns if c.name not in keys})
    elif name == "sqlite":
        stmt = sqlite.insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(index_elements=keys,
                                          set_={c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys})
    else:
        raise NotImplementedError(f"no upsert for {name}")
    with engine.begin() as c:
        c.execute(stmt)


def sync(con, engine) -> dict:
    """Copy tests and alerts from the local SQLite store into the target database. Safe to re-run."""
    test_rows = [{k: r[k] for k in ("doc", "period", "metric", "kind", "actual", "operator", "limit_value", "status",
                                   "headroom_pct", "projected_next")} for r in con.execute("SELECT * FROM tests")]
    alert_rows = [{"alert_key": r["key"], **{k: r[k] for k in ("doc", "date", "severity", "kind", "title", "detail",
                                                                "evidence", "status")}}
                  for r in con.execute("SELECT * FROM alerts")]
    _upsert(engine, tests, test_rows, ["doc", "period", "metric", "kind"])
    _upsert(engine, alerts, alert_rows, ["alert_key"])
    return {"tests": len(test_rows), "alerts": len(alert_rows)}


def latest(engine, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM cw_v_latest" + (" WHERE status = :s" if status else "") + " ORDER BY doc, kind, metric"
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(q), {"s": status} if status else {})]


def open_alerts(engine) -> list[dict]:
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(select(alerts).where(alerts.c.status == "open")
                                                    .order_by(alerts.c.severity, alerts.c.date.desc()))]


if __name__ == "__main__":
    from covenantwatch.db import connect

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("COVENANTWATCH_SQL_URL"), required=not os.getenv("COVENANTWATCH_SQL_URL"))
    eng = engine_for(ap.parse_args().url)
    create_schema(eng)
    print(sync(connect(), eng))
