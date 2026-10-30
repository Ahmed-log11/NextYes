"""Check functions. Each takes a snapshot and the rule's params and returns
(passed, evidence). Policies pick checks by name, so adding a lender is YAML only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import finance
from .models import FinancialSnapshot

Evidence = dict[str, Any]
Check = Callable[[FinancialSnapshot, dict[str, Any]], tuple[bool, Evidence]]

CHECKS: dict[str, Check] = {}


def check(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        if name in CHECKS:
            raise ValueError(f"check {name} registered twice")
        CHECKS[name] = fn
        return fn

    return register


@check("cr_valid")
def cr_valid(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    return s.cr_active and s.cr_days_left > 0, {"days_left": s.cr_days_left, "active": s.cr_active}


@check("cr_not_expiring")
def cr_not_expiring(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    # An already-expired registration is reported by cr_valid; don't count it twice.
    days = s.cr_days_left
    expiring = 0 < days < p["min_days"]
    return not expiring, {"days_left": days, "min_days": p["min_days"]}


@check("min_operating_history")
def min_operating_history(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    return s.operating_months >= p["min_months"], {
        "operating_months": s.operating_months,
        "min_months": p["min_months"],
    }


@check("no_active_defaults")
def no_active_defaults(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    return not s.has_active_defaults, {"has_active_defaults": s.has_active_defaults}


@check("cashflow_consistency")
def cashflow_consistency(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    cv = s.revenue_cv
    ok = cv <= p["max_cv"] and s.zero_revenue_months <= p["max_zero_months"]
    return ok, {
        "revenue_cv": round(cv, 3),
        "max_cv": p["max_cv"],
        "zero_months": s.zero_revenue_months,
    }


@check("dscr_min")
def dscr_min(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    ratio = finance.dscr(s)
    cap = finance.max_affordable_amount(s, p["min_dscr"])
    return ratio >= p["min_dscr"], {
        "dscr": round(ratio, 2),
        "min_dscr": p["min_dscr"],
        "requested_sar": round(s.request.amount_sar),
        "max_affordable_sar": round(max(cap, 0.0), -3),
    }


@check("flag")
def flag(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    """Generic yes/no fact on the snapshot, e.g. einvoicing_compliant."""
    field = p["field"]
    value = getattr(s, field)
    if not isinstance(value, bool):
        raise TypeError(f"flag check needs a boolean field, {field} is {type(value).__name__}")
    return value, {field: value}


@check("security")
def security(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    return s.collateral_available or s.kafalah_guarantee, {
        "collateral_available": s.collateral_available,
        "kafalah_guarantee": s.kafalah_guarantee,
    }


@check("min_annual_revenue")
def min_annual_revenue(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    rev = s.annual_revenue_sar
    return rev >= p["min_sar"], {"annual_revenue_sar": round(rev), "min_sar": p["min_sar"]}


@check("receivables_overdue")
def receivables_overdue(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    ratio = s.overdue_receivables_ratio
    return ratio <= p["max_ratio"], {
        "overdue_ratio": round(ratio, 3),
        "max_ratio": p["max_ratio"],
        "overdue_sar": round(s.receivables_overdue_90d_sar),
    }


@check("is_sme")
def is_sme(s: FinancialSnapshot, p: dict[str, Any]) -> tuple[bool, Evidence]:
    cls = finance.size_class(s.annual_revenue_sar)
    return cls != "not_sme", {"size_class": cls}
