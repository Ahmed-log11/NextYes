"""Issues we can plant in a healthy business.

Each issue code matches a rule id in the lender policies, so the ground truth
is simple: plant CR_EXPIRING, and the bank policy must report CR_EXPIRING.
Issues edit the raw business data (a dict) before it becomes a snapshot.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any

Data = dict[str, Any]
Mutator = Callable[[Data, random.Random, date], None]

ISSUES: dict[str, Mutator] = {}


def issue(code: str) -> Callable[[Mutator], Mutator]:
    def register(fn: Mutator) -> Mutator:
        ISSUES[code] = fn
        return fn

    return register


# ---- Revenue-shaping issues run first: the request is sized after them ----

@issue("REVENUE_LOW")
def revenue_low(d: Data, rng: random.Random, as_of: date) -> None:
    """Annual revenue under SAR 2M (fails the digital lender only)."""
    target = rng.uniform(1_000_000, 1_800_000)
    scale = target / sum(d["monthly_revenue_sar"])
    d["monthly_revenue_sar"] = [round(x * scale, -2) for x in d["monthly_revenue_sar"]]


@issue("CASHFLOW_VOLATILE")
def cashflow_volatile(d: Data, rng: random.Random, as_of: date) -> None:
    """Large month-to-month swings, keeping the yearly total about the same."""
    rev = d["monthly_revenue_sar"]
    base = mean(rev)
    for _ in range(50):
        factors = [rng.choice([0.35, 0.5, 0.7, 1.4, 1.6, 1.8]) for _ in rev]
        norm = mean(factors)
        candidate = [round(x * f / norm, -2) for x, f in zip(rev, factors)]
        if pstdev(candidate) / mean(candidate) >= 0.5:
            d["monthly_revenue_sar"] = candidate
            return
    raise RuntimeError(f"could not make revenue volatile from base {base}")


# ---- Everything else ----

@issue("CR_INVALID")
def cr_invalid(d: Data, rng: random.Random, as_of: date) -> None:
    if rng.random() < 0.5:
        d["cr_expiry"] = (as_of - timedelta(days=rng.randint(5, 120))).isoformat()
    else:
        d["cr_active"] = False


@issue("CR_EXPIRING")
def cr_expiring(d: Data, rng: random.Random, as_of: date) -> None:
    d["cr_expiry"] = (as_of + timedelta(days=rng.randint(10, 80))).isoformat()


@issue("HISTORY_SHORT")
def history_short(d: Data, rng: random.Random, as_of: date) -> None:
    # Half the time young enough for the digital lender (12+ months) but not the bank (24+).
    d["operating_months"] = rng.randint(13, 22) if rng.random() < 0.5 else rng.randint(6, 11)


@issue("ACTIVE_DEFAULTS")
def active_defaults(d: Data, rng: random.Random, as_of: date) -> None:
    d["has_active_defaults"] = True


@issue("EINVOICING")
def einvoicing(d: Data, rng: random.Random, as_of: date) -> None:
    d["einvoicing_compliant"] = False


@issue("VAT_LATE")
def vat_late(d: Data, rng: random.Random, as_of: date) -> None:
    d["vat_filed_on_time"] = False


@issue("STATEMENTS_MISSING")
def statements_missing(d: Data, rng: random.Random, as_of: date) -> None:
    d["financial_statements_available"] = False


@issue("ACCOUNTS_MIXED")
def accounts_mixed(d: Data, rng: random.Random, as_of: date) -> None:
    d["separate_business_account"] = False


@issue("NO_SECURITY")
def no_security(d: Data, rng: random.Random, as_of: date) -> None:
    d["collateral_available"] = False
    d["kafalah_guarantee"] = False


@issue("RECEIVABLES_OVERDUE")
def receivables_overdue(d: Data, rng: random.Random, as_of: date) -> None:
    d["receivables_overdue_90d_sar"] = round(d["receivables_outstanding_sar"] * rng.uniform(0.35, 0.6), -2)


# DSCR_LOW is applied by the generator when it sizes the request.
DSCR_LOW = "DSCR_LOW"

ALL_CODES: tuple[str, ...] = (*ISSUES.keys(), DSCR_LOW)
REVENUE_SHAPING = ("REVENUE_LOW", "CASHFLOW_VOLATILE")

# Pairs that cannot both be true: a registration is either expired or about to expire.
EXCLUSIVE: tuple[frozenset[str], ...] = (frozenset({"CR_INVALID", "CR_EXPIRING"}),)


def compatible(codes: set[str] | frozenset[str]) -> bool:
    return not any(pair <= set(codes) for pair in EXCLUSIVE)
