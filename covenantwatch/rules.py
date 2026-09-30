"""Declarative, versioned rules engine for covenant and policy tests.

The thresholds live in rules.json, validated on load, so a rule change is a reviewed data change, not a code edit.
Every evaluation returns a Decision that says which rule fired, with the inputs it used, so any alert can be explained
("why is this amber?") and audited against the rules version that produced it.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RULES_PATH = Path(__file__).with_name("rules.json")
Status = Literal["green", "amber", "red"]


class RuleSet(BaseModel):
    version: str
    early_warning_headroom: float = Field(gt=0, lt=1)
    projection_band: float = Field(ge=0, lt=1)
    severity: dict[Literal["covenant", "policy"], dict[Literal["red", "amber"], Literal["high", "medium", "low"]]]
    policy_triggers: dict[str, tuple[Literal["<=", ">="], float]]
    status_rules: list[dict]

    @field_validator("severity")
    @classmethod
    def both_kinds(cls, v):
        if set(v) != {"covenant", "policy"}:
            raise ValueError("severity must define both 'covenant' and 'policy'")
        return v


class Decision(BaseModel):
    status: Status
    rule_id: str
    headroom_pct: float
    actual: float
    operator: str
    limit: float
    projected: float | None
    rules_version: str
    reason: str


@lru_cache
def load_rules(path: str | None = None) -> RuleSet:
    return RuleSet.model_validate(json.loads(Path(path or RULES_PATH).read_text(encoding="utf-8")))


def evaluate(actual: float, op: str, limit: float, projected: float | None = None, rules: RuleSet | None = None) -> Decision:
    rules = rules or load_rules()
    if op == "<=":
        headroom = (limit - actual) / limit
        breach = actual > limit
        trending = projected is not None and projected >= (1 - rules.projection_band) * limit
    elif op == ">=":
        headroom = (actual - limit) / limit
        breach = actual < limit
        trending = projected is not None and projected <= (1 + rules.projection_band) * limit
    else:
        raise ValueError(f"unknown operator {op!r}")

    pct = round(headroom * 100, 1)
    if breach:
        status, rule, reason = "red", "R1_BREACH", f"{actual:.2f} is outside the limit {op} {limit}"
    elif headroom < rules.early_warning_headroom:
        status, rule, reason = "amber", "R2_LOW_HEADROOM", f"headroom {pct}% is below the {rules.early_warning_headroom:.0%} early-warning line"
    elif trending:
        status, rule, reason = "amber", "R3_TREND_TO_LIMIT", f"trend projects {projected:.2f}, within {rules.projection_band:.0%} of the limit {limit}"
    else:
        status, rule, reason = "green", "R4_WITHIN_LIMITS", f"headroom {pct}% and no breach projected"
    return Decision(status=status, rule_id=rule, headroom_pct=pct, actual=actual, operator=op, limit=limit,
                    projected=projected, rules_version=rules.version, reason=reason)


def severity(kind: str, status: str, rules: RuleSet | None = None) -> str | None:
    """Alert severity for a status change; None for green (no alert)."""
    return (rules or load_rules()).severity[kind].get(status)
