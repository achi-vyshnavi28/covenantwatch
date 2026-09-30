"""DynamoDB access patterns, tested against moto's local DynamoDB (no AWS account needed)."""
import boto3
import pytest
from moto import mock_aws

from covenantwatch.dynamo_store import AlertStore, create_table, mirror_alerts


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        create_table("alerts")
        yield AlertStore("alerts", resource=boto3.resource("dynamodb"))


def alert(key, doc="madhur_steel", date="2027-05-10", severity="high"):
    return {"key": key, "doc": doc, "date": date, "severity": severity, "kind": "breach", "title": key, "detail": "d"}


def test_put_is_idempotent(store):
    assert store.put_alert(alert("a1")) is True
    assert store.put_alert(alert("a1")) is False
    assert len(store.alerts_for_borrower("madhur_steel")) == 1


def test_borrower_query_is_newest_first(store):
    store.put_alert(alert("old", date="2027-01-01"))
    store.put_alert(alert("new", date="2027-06-01"))
    store.put_alert(alert("other", doc="anchor_offshore"))
    assert [a["key"] for a in store.alerts_for_borrower("madhur_steel")] == ["new", "old"]


def test_open_alerts_most_severe_first_and_status_moves(store):
    store.put_alert(alert("low", severity="low"))
    store.put_alert(alert("high", severity="high", doc="anchor_offshore"))
    store.put_alert(alert("med", severity="medium"))
    assert [a["key"] for a in store.alerts_by_status("open")] == ["high", "med", "low"]
    store.set_status(alert("med", severity="medium"), "resolved")
    assert [a["key"] for a in store.alerts_by_status("open")] == ["high", "low"]
    assert [a["key"] for a in store.alerts_by_status("resolved")] == ["med"]


def test_mirror_from_sqlite_is_safe_to_rerun(store, tmp_path):
    from covenantwatch.db import connect, raise_alert
    con = connect(tmp_path / "t.sqlite3")
    raise_alert(con, "k1", doc="atomberg", date="2027-03-01", severity="medium", kind="late", title="t", detail="d")
    raise_alert(con, "k2", doc="atomberg", date="2027-04-01", severity="high", kind="breach", title="t", detail="d")
    assert mirror_alerts(con, store) == 2
    assert mirror_alerts(con, store) == 0
