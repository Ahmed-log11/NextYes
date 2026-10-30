"""Lender policies: loaded from YAML so they can be swapped without code changes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .models import Severity

POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"


class RuleSpec(BaseModel):
    id: str = Field(description="Blocker code shown to the user, e.g. CR_EXPIRING")
    check: str = Field(description="Name of the check function in rules.py")
    severity: Severity
    weight: float = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(description="Shown when the rule fails; {placeholders} filled from evidence")
    source: str
    source_url: str | None = None
    assumption: bool = Field(
        default=False, description="True when the threshold is ours, not from a public source"
    )


class Policy(BaseModel):
    id: str
    name: str
    name_ar: str = ""
    description: str
    ready_threshold: float = Field(ge=0, le=100)
    rules: list[RuleSpec]
    version: str = ""

    def rule(self, rule_id: str) -> RuleSpec:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(rule_id)


def load_policy(name_or_path: str | Path) -> Policy:
    """Load by id (`commercial_bank_sme`) or by explicit path."""
    path = Path(name_or_path)
    if not path.suffix:
        path = POLICY_DIR / f"{name_or_path}.yaml"
    raw = path.read_bytes()
    policy = Policy.model_validate(yaml.safe_load(raw))
    policy.version = hashlib.sha256(raw).hexdigest()[:12]
    ids = [r.id for r in policy.rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate rule ids in {path.name}")
    return policy


def available_policies() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.yaml"))
