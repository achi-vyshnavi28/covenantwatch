"""Relational sync to PostgreSQL / MySQL. Runs on SQLite always, and on PostgreSQL and MySQL when
COVENANTWATCH_TEST_PG_URL / COVENANTWATCH_TEST_MYSQL_URL are set (CI service containers)."""
import os

import pytest

from covenantwatch import sql_mirror
from covenantwatch.db import connect, raise_alert

URLS = ["sqlite://"] + [os.environ[k] for k in ("COVENANTWATCH_TEST_PG_URL", "COVENANTWATCH_TEST_MYSQL_URL") if os.getenv(k)]


@pytest.fixture(params=URLS, ids=lambda u: u.split(":")[0])
def target(request):
    eng = sql_mirror.engine_for(request.param)
    with eng.begin() as c:
        for v in sql_mirror.VIEWS:
            c.exec_driver_sql(f"DROP VIEW IF EXISTS {v}")
    sql_mirror.metadata.drop_all(eng)
    sql_mirror.create_schema(eng)
    return eng


@pytest.fixture
def local(tmp_path):
    con = connect(tmp_path / "cw.sqlite3")
    rows = [("madhur_steel", "FY2027-Q1", "debt_to_equity", "covenant", 2.6, "<=", 3.33, "green", 21.9, None),
            ("madhur_steel", "FY2027-Q2", "debt_to_equity", "covenant", 3.1, "<=", 3.33, "amber", 6.9, 3.6),
            ("madhur_steel", "FY2027-Q3", "debt_to_equity", "covenant", 3.5, "<=", 3.33, "red", -5.1, None),
            ("atomberg", "FY2027-Q3", "interest_cover", "policy", 1.2, ">=", 1.5, "red", -20.0, None)]
    con.executemany("INSERT INTO tests VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    raise_alert(con, "madhur_steel|covenant|debt_to_equity|FY2027-Q3", doc="madhur_steel", date="2027-01-05",
                severity="high", kind="covenant_red", title="debt to equity BREACH", detail="3.5 vs 3.33")
    con.commit()
    return con


def test_sync_and_window_views(target, local):
    assert sql_mirror.sync(local, target) == {"tests": 4, "alerts": 1}
    latest = {(r["doc"], r["metric"]): r for r in sql_mirror.latest(target)}
    assert latest[("madhur_steel", "debt_to_equity")]["period"] == "FY2027-Q3"          # ROW_NUMBER picks the newest
    assert [r["doc"] for r in sql_mirror.latest(target, status="red")] == ["atomberg", "madhur_steel"]
    with target.connect() as c:
        change = c.exec_driver_sql("SELECT change_vs_prev FROM cw_v_trend WHERE period = 'FY2027-Q3' "
                                   "AND doc = 'madhur_steel'").scalar()
    assert round(change, 2) == 0.4                                                     # LAG versus the previous quarter


def test_resync_is_idempotent_and_updates_in_place(target, local):
    sql_mirror.sync(local, target)
    local.execute("UPDATE alerts SET status = 'resolved'")
    local.commit()
    assert sql_mirror.sync(local, target) == {"tests": 4, "alerts": 1}
    assert sql_mirror.open_alerts(target) == []
    with target.connect() as c:
        assert c.exec_driver_sql("SELECT COUNT(*) FROM cw_alerts").scalar() == 1
        assert c.exec_driver_sql("SELECT COUNT(*) FROM cw_tests").scalar() == 4
