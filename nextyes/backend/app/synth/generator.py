"""Generate one synthetic business: healthy first, then plant the requested issues.

Same (seed, issues) → identical business, every time.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel

from ..engine import FinancialSnapshot, assess, available_policies, load_policy
from ..engine import finance
from .issues import DSCR_LOW, ISSUES, REVENUE_SHAPING, compatible
from .profiles import CITIES, NAME_STEMS, SECTORS

AS_OF = date(2026, 10, 30)
MIN_DSCR = 1.2  # both policies use 1.2; requests are sized against it


class BusinessMeta(BaseModel):
    business_id: str
    seed: int
    name_en: str
    name_ar: str
    sector: str
    sector_en: str
    sector_ar: str
    city_en: str
    city_ar: str
    planted_issues: list[str]


class PolicyTruth(BaseModel):
    ready: bool
    score: float
    blockers: list[str]


class SyntheticBusiness(BaseModel):
    meta: BusinessMeta
    snapshot: FinancialSnapshot

    def truth(self) -> dict[str, PolicyTruth]:
        """Expected engine result per policy, from the TRUE snapshot.

        Evaluation later compares this with what the agent concludes after
        reading the business's documents.
        """
        out = {}
        for name in available_policies():
            a = assess(self.snapshot, load_policy(name))
            out[name] = PolicyTruth(ready=a.ready, score=a.score, blockers=a.blocker_codes)
        return out


def _healthy(rng: random.Random, sector_idx: int) -> dict[str, Any]:
    sector = SECTORS[sector_idx]
    base = rng.randint(*sector.monthly_revenue_sar)
    first_month = AS_OF.month % 12  # 12 months ending with the as-of month
    revenue = [
        round(base * sector.seasonality[(first_month + i) % 12] * rng.uniform(0.95, 1.05), -2)
        for i in range(12)
    ]
    outstanding = round(base * rng.uniform(0.8, 2.0), -2)
    has_collateral = rng.random() < 0.3
    return {
        "as_of": AS_OF.isoformat(),
        "cr_active": True,
        "cr_expiry": (AS_OF + timedelta(days=rng.randint(150, 700))).isoformat(),
        "operating_months": rng.randint(30, 150),
        "monthly_revenue_sar": revenue,
        "operating_margin": round(rng.uniform(*sector.operating_margin), 3),
        "existing_monthly_debt_service_sar": rng.choice([0, round(base * rng.uniform(0.01, 0.03), -2)]),
        "has_active_defaults": False,
        "receivables_outstanding_sar": outstanding,
        "receivables_overdue_90d_sar": round(outstanding * rng.uniform(0.0, 0.15), -2),
        "einvoicing_compliant": True,
        "vat_filed_on_time": True,
        "financial_statements_available": True,
        "separate_business_account": True,
        "collateral_available": has_collateral,
        "kafalah_guarantee": not has_collateral,
    }


def _size_request(d: dict[str, Any], rng: random.Random, too_big: bool) -> None:
    tenor = rng.choice([36, 48, 60])
    rate = round(rng.uniform(0.07, 0.11), 3)
    d["request"] = {"amount_sar": 1.0, "tenor_months": tenor, "annual_profit_rate": rate}
    probe = FinancialSnapshot.model_validate({"business_id": "probe", **d})
    cap = finance.max_affordable_amount(probe, MIN_DSCR)
    if cap < 100_000:  # existing debt eats the room; clear it so the business is fundable
        d["existing_monthly_debt_service_sar"] = 0
        probe = FinancialSnapshot.model_validate({"business_id": "probe", **d})
        cap = finance.max_affordable_amount(probe, MIN_DSCR)
    factor = rng.uniform(1.35, 2.0) if too_big else rng.uniform(0.55, 0.85)
    d["request"]["amount_sar"] = round(cap * factor, -4)


def make_business(
    business_id: str,
    seed: int,
    issues: list[str],
    *,
    sector: str | None = None,
) -> SyntheticBusiness:
    unknown = set(issues) - set(ISSUES) - {DSCR_LOW}
    if unknown:
        raise ValueError(f"unknown issues: {sorted(unknown)}")
    if not compatible(set(issues)):
        raise ValueError(f"issues cannot all be true at once: {sorted(issues)}")

    rng = random.Random(seed)
    sector_idx = (
        [s.key for s in SECTORS].index(sector) if sector else rng.randrange(len(SECTORS))
    )
    s = SECTORS[sector_idx]
    city_en, city_ar = rng.choice(CITIES)
    stem_en, stem_ar = rng.choice(NAME_STEMS)

    data = _healthy(rng, sector_idx)
    ordered = [c for c in REVENUE_SHAPING if c in issues] + sorted(
        c for c in issues if c not in REVENUE_SHAPING and c != DSCR_LOW
    )
    for code in ordered:
        ISSUES[code](data, rng, AS_OF)
    _size_request(data, rng, too_big=DSCR_LOW in issues)

    meta = BusinessMeta(
        business_id=business_id,
        seed=seed,
        name_en=f"{stem_en} {s.name_suffix_en}",
        name_ar=f"{stem_ar} {s.name_suffix_ar}" if s.key != "clinic" else f"عيادة {stem_ar} {s.name_suffix_ar}",
        sector=s.key,
        sector_en=s.label_en,
        sector_ar=s.label_ar,
        city_en=city_en,
        city_ar=city_ar,
        planted_issues=sorted(issues),
    )
    snapshot = FinancialSnapshot.model_validate({"business_id": business_id, **data})
    return SyntheticBusiness(meta=meta, snapshot=snapshot)
