"""Offline tests: temporary database, classifier replaced by keyword rules (no API key needed)."""

import json

import pytest

import covenantwatch.monitor as monitor
from covenantwatch.classify import keyword
from covenantwatch.config import DATA
from covenantwatch.db import connect
from covenantwatch.extract import pages, score, squash
from covenantwatch.simulate import build

REGISTER = [
    {"doc": "madhur_steel", "topic": "FIN_DEBT_EQUITY", "category": "financial", "lender": "RBL Bank", "description": "", "operator": "<=",
     "threshold": 3.33, "deadline": None, "page": 430, "quote": "Debt-to-Equity ratio of 3.33:1 to be maintained", "status": "confirmed"},
    {"doc": "madhur_steel", "topic": "FIN_SECURITY_COVER", "category": "financial", "lender": "Bajaj", "description": "", "operator": ">=",
     "threshold": 1.33, "deadline": None, "page": 431, "quote": "minimum security coverage of 1.33X", "status": "confirmed"},
    {"doc": "madhur_steel", "topic": "CON_FRESH_BORROWING", "category": "consent", "lender": None, "description": "", "operator": None,
     "threshold": None, "deadline": None, "page": 441, "quote": "intimating the bank prior to availing any fresh loans", "status": "confirmed"},
    {"doc": "atomberg", "topic": "CON_INVESTMENTS", "category": "consent", "lender": None, "description": "", "operator": None,
     "threshold": None, "deadline": None, "page": 389, "quote": "to make any investments", "status": "confirmed"},
]


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "classify", lambda text: (keyword(text), "keyword"))
    c = connect(tmp_path / "t.sqlite3")
    yield c
    c.close()


def test_register_quotes_exist_on_their_pages():
    for c in REGISTER:
        assert squash(c["quote"]) in squash(pages(c["doc"])[c["page"]])


def test_status_rules():
    assert monitor.status(3.48, "<=", 3.33, None)[0] == "red"
    assert monitor.status(2.55, "<=", 3.33, 3.30)[0] == "amber"  # 23% headroom but trending to 99% of the limit
    assert monitor.status(1.80, "<=", 3.33, 1.95)[0] == "green"
    assert monitor.status(1.45, ">=", 1.33, 1.28)[0] == "amber"
    assert monitor.status(1.30, ">=", 1.33, None)[0] == "red"


def test_monitor_catches_planted_problems_once(con):
    feed = build()
    keys = set(monitor.run("2027-03-31", con=con, feed=feed, register=REGISTER, send=False))
    assert {"madhur_steel|covenant|debt_to_equity|FY2027-Q3", "madhur_steel|covenant|security_cover|FY2027-Q3",
            "madhur_steel|integrity|debt_to_equity|FY2027-Q2", "madhur_steel|reporting|stock_statement|2026-11|RBL Bank",
            "madhur_steel|reporting|stock_statement|2027-02|Bajaj Finance", "madhur_steel|event|CON_FRESH_BORROWING|EV02",
            "atomberg|event|CON_INVESTMENTS|EV06", "atomberg|policy|interest_cover|FY2024"} <= keys
    assert not any("EV03" in k or "EV07" in k for k in keys)  # consent obtained: no alert
    assert not any(k.endswith(("EV01", "EV05", "EV08")) for k in keys)  # routine news: no alert
    assert monitor.run("2027-03-31", con=con, feed=feed, register=REGISTER, send=False) == []  # idempotent


def test_reporting_deadline_differs_by_lender(con):
    keys = monitor.run("2026-09-30", con=con, feed=build(), register=REGISTER, send=False)
    assert "madhur_steel|reporting|stock_statement|2026-08|Bajaj Finance" in keys  # sent 22nd, due 20th
    assert "madhur_steel|reporting|stock_statement|2026-08|RBL Bank" not in keys  # due 25th: on time


def test_nothing_before_it_happens(con):
    keys = monitor.run("2026-06-30", con=con, feed=build(), register=REGISTER, send=False)
    assert not any("FY2027-Q3" in k or "EV02" in k for k in keys)


def test_sql_views(con):
    monitor.run("2027-03-31", con=con, feed=build(), register=REGISTER, send=False)
    latest = {(r["doc"], r["metric"], r["kind"]): r["period"] for r in con.execute("SELECT * FROM v_latest")}
    assert latest[("madhur_steel", "debt_to_equity", "covenant")] == "FY2027-Q4"
    trend = con.execute("SELECT change_vs_prev FROM v_trend WHERE doc='madhur_steel' AND metric='debt_to_equity' AND period='FY2027-Q3'").fetchone()
    assert trend[0] == pytest.approx(3.48 - 2.55, abs=0.01)


def test_keyword_classifier_baseline():
    assert keyword("ICRA announced a downgrade of the long-term rating") == "EOD_RATING_DOWNGRADE"
    assert keyword("The company launched a new fan") == "NONE"


def test_extraction_scoring():
    kept = [{"topic": "FIN_DEBT_EQUITY", "threshold": 3.33, "operator": "<="}, {"topic": "CON_DIVIDEND", "threshold": None, "operator": None}]
    s = score("madhur_steel", kept)
    assert s["precision"] == 1.0 and s["financial_thresholds_exact"]["FIN_DEBT_EQUITY"] is True
    assert s["financial_thresholds_exact"]["FIN_SECURITY_COVER"] is False


def test_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import covenantwatch.api as api
    import covenantwatch.db as db

    path = tmp_path / "api.sqlite3"
    monkeypatch.setattr(api, "connect", lambda: db.connect(path))
    monkeypatch.setattr(monitor, "classify", lambda text: (keyword(text), "keyword"))
    monkeypatch.setattr(api, "run", lambda as_of, con=None: monitor.run(as_of, con=con or db.connect(path), feed=build(), register=REGISTER, send=False))
    c = TestClient(api.app)
    assert c.post("/run", params={"as_of": "2027-03-31"}).status_code == 200
    alerts = c.get("/alerts").json()
    assert alerts and alerts[0]["severity"] == "high"
    k = alerts[0]["key"]
    assert c.post(f"/alerts/{k}/feedback", json={"verdict": "false_positive"}).json()["status"] == "dismissed"
    assert c.get("/register/nope").status_code == 404
    assert c.post("/register/madhur_steel/confirm").json()["confirmed"] == 0  # already confirmed
