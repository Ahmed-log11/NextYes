"""The readiness engine: deterministic scoring of a snapshot against a policy.

The language model never changes these results. It may explain them and plan
around them, but the score, the blockers and `ready` all come from here.
"""

from __future__ import annotations

from . import finance
from .models import Assessment, FinancialSnapshot, Finding
from .policy import Policy, RuleSpec
from .rules import CHECKS


def _evaluate(rule: RuleSpec, s: FinancialSnapshot) -> Finding:
    try:
        fn = CHECKS[rule.check]
    except KeyError:
        raise KeyError(f"policy rule {rule.id} uses unknown check '{rule.check}'") from None
    passed, evidence = fn(s, rule.params)
    return Finding(
        code=rule.id,
        passed=passed,
        severity=rule.severity,
        weight=rule.weight,
        message="" if passed else rule.message.format_map(evidence),
        evidence=evidence,
        source=rule.source,
        assumption=rule.assumption,
    )


def assess(s: FinancialSnapshot, policy: Policy) -> Assessment:
    findings = [_evaluate(r, s) for r in policy.rules]

    total = sum(f.weight for f in findings)
    earned = sum(f.weight for f in findings if f.passed)
    score = round(100 * earned / total, 1) if total else 0.0

    blockers = [f for f in findings if not f.passed]
    # Hard blockers first, then by weight, so the most important reason leads.
    blockers.sort(key=lambda f: (f.severity != "hard", -f.weight))
    hard_fail = any(f.severity == "hard" for f in blockers)

    metrics: dict[str, float | str | None] = {
        "annual_revenue_sar": round(s.annual_revenue_sar),
        "revenue_cv": round(s.revenue_cv, 3),
        "dscr": round(finance.dscr(s), 2),
        "size_class": finance.size_class(s.annual_revenue_sar),
        "max_affordable_sar": None,
    }
    for r in policy.rules:
        if r.check == "dscr_min":
            cap = finance.max_affordable_amount(s, r.params["min_dscr"])
            metrics["max_affordable_sar"] = round(max(cap, 0.0), -3)

    return Assessment(
        business_id=s.business_id,
        policy_id=policy.id,
        policy_version=policy.version,
        as_of=s.as_of,
        score=score,
        ready=(not hard_fail) and score >= policy.ready_threshold,
        ready_threshold=policy.ready_threshold,
        blockers=blockers,
        passed=[f for f in findings if f.passed],
        metrics=metrics,
    )
