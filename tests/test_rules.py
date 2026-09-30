"""Rules engine: table-driven decisions, explanations, versioning and validation."""
import json

import pytest
from pydantic import ValidationError

from covenantwatch.rules import RuleSet, evaluate, load_rules, severity


@pytest.mark.parametrize("actual, op, limit, projected, status, rule", [
    (3.48, "<=", 3.33, None, "red", "R1_BREACH"),
    (3.10, "<=", 3.33, None, "amber", "R2_LOW_HEADROOM"),       # 7% headroom
    (2.55, "<=", 3.33, 3.30, "amber", "R3_TREND_TO_LIMIT"),      # 23% headroom but trending to 99% of the limit
    (1.80, "<=", 3.33, 1.95, "green", "R4_WITHIN_LIMITS"),
    (1.30, ">=", 1.33, None, "red", "R1_BREACH"),
    (1.45, ">=", 1.33, 1.28, "amber", "R2_LOW_HEADROOM"),
    (2.00, ">=", 1.33, 1.38, "amber", "R3_TREND_TO_LIMIT"),
    (7.33, ">=", 1.50, None, "green", "R4_WITHIN_LIMITS"),
])
def test_each_rule_fires_where_expected(actual, op, limit, projected, status, rule):
    d = evaluate(actual, op, limit, projected)
    assert (d.status, d.rule_id) == (status, rule)


def test_decision_explains_itself_and_records_rules_version():
    d = evaluate(3.10, "<=", 3.33)
    assert d.rules_version == load_rules().version
    assert "headroom 6.9%" in d.reason and "15% early-warning" in d.reason
    assert d.model_dump()["limit"] == 3.33


def test_severity_matrix():
    assert severity("covenant", "red") == "high"
    assert severity("policy", "amber") == "low"
    assert severity("covenant", "green") is None


def test_changing_the_rules_file_changes_decisions(tmp_path):
    data = json.loads(load_rules().model_dump_json())
    data.update(version="test", early_warning_headroom=0.05)
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data))
    stricter = load_rules(str(path))
    d = evaluate(3.10, "<=", 3.33, rules=stricter)  # 7% headroom is now above the 5% line
    assert (d.status, d.rules_version) == ("green", "test")


def test_invalid_rules_are_rejected_on_load():
    bad = json.loads(load_rules().model_dump_json())
    bad["early_warning_headroom"] = 1.5
    with pytest.raises(ValidationError):
        RuleSet.model_validate(bad)
    with pytest.raises(ValueError):
        evaluate(1.0, "==", 1.0)
