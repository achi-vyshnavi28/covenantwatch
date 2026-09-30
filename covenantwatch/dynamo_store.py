"""DynamoDB store for alerts, designed around the questions the dashboard and Slack bot ask.

Single-table design, one item per alert:
    PK = BORROWER#<doc>          SK = ALERT#<date>#<key>          -> "all alerts for a borrower, newest first"
    GSI1PK = STATUS#<status>     GSI1SK = <severity rank>#<date>  -> "open alerts, most severe first" across the portfolio

Writes are conditional (attribute_not_exists), so re-running the daily job never duplicates an alert, the same
idempotency the SQLite store gets from INSERT OR IGNORE. Enable by setting COVENANTWATCH_DYNAMO_TABLE.
"""
import os

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

SEVERITY_RANK = {"high": "0", "medium": "1", "low": "2"}


def create_table(name, client=None):
    client = client or boto3.client("dynamodb")
    client.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                               {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}])


class AlertStore:
    def __init__(self, table_name=None, resource=None):
        self.table = (resource or boto3.resource("dynamodb")).Table(table_name or os.environ["COVENANTWATCH_DYNAMO_TABLE"])

    @staticmethod
    def _item(alert):
        status = alert.get("status", "open")
        return {
            "PK": f"BORROWER#{alert['doc']}", "SK": f"ALERT#{alert['date']}#{alert['key']}",
            "GSI1PK": f"STATUS#{status}", "GSI1SK": f"{SEVERITY_RANK.get(alert['severity'], '9')}#{alert['date']}",
            **{k: str(v) for k, v in alert.items() if v is not None}, "status": status,
        }

    def put_alert(self, alert):
        """Insert once. Returns True only for a new alert, so notifications still fire exactly once."""
        try:
            self.table.put_item(Item=self._item(alert), ConditionExpression="attribute_not_exists(PK)")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def alerts_for_borrower(self, doc, limit=50):
        r = self.table.query(KeyConditionExpression=Key("PK").eq(f"BORROWER#{doc}") & Key("SK").begins_with("ALERT#"),
                             ScanIndexForward=False, Limit=limit)
        return r["Items"]

    def alerts_by_status(self, status="open", limit=100):
        r = self.table.query(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq(f"STATUS#{status}"),
                             ScanIndexForward=True, Limit=limit)
        return r["Items"]

    def set_status(self, alert, status):
        item = self._item({**alert, "status": status})
        self.table.update_item(
            Key={"PK": item["PK"], "SK": item["SK"]},
            UpdateExpression="SET #s = :s, GSI1PK = :g",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status, ":g": item["GSI1PK"]},
            ConditionExpression="attribute_exists(PK)")


def mirror_alerts(con, store):
    """Copy SQLite alerts into DynamoDB (safe to re-run). Returns how many were new."""
    return sum(store.put_alert(dict(r)) for r in con.execute(
        "SELECT key, doc, date, severity, kind, title, detail, evidence, status FROM alerts"))
