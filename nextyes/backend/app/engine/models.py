"""Data models for the readiness engine.

The engine never reads raw documents. It reads a `FinancialSnapshot`: the
structured facts about one business at one point in time. Extraction (from
PDFs) and the simulator both produce snapshots; the engine only scores them.
"""

from __future__ import annotations

from datetime import date
from statistics import mean, pstdev
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["hard", "soft"]
SizeClass = Literal["micro", "small", "medium", "not_sme"]


class FinancingRequest(BaseModel):
    amount_sar: float = Field(gt=0)
    tenor_months: int = Field(gt=0, le=120)
    annual_profit_rate: float = Field(ge=0, le=1, description="e.g. 0.09 for 9%")


class FinancialSnapshot(BaseModel):
    """Facts about one business, as of one date."""

    business_id: str
    as_of: date

    # Registration
    cr_active: bool
    cr_expiry: date
    operating_months: int = Field(ge=0)

    # Cash flow: the last 12 months of operating deposits, oldest first
    monthly_revenue_sar: list[float] = Field(min_length=12, max_length=12)
    operating_margin: float = Field(
        ge=0, le=1, description="Share of revenue left after operating costs"
    )

    # Existing obligations and credit record
    existing_monthly_debt_service_sar: float = Field(ge=0)
    has_active_defaults: bool

    # Receivables
    receivables_outstanding_sar: float = Field(ge=0)
    receivables_overdue_90d_sar: float = Field(ge=0)

    # Compliance and records
    einvoicing_compliant: bool
    vat_filed_on_time: bool
    financial_statements_available: bool
    separate_business_account: bool

    # Security
    collateral_available: bool
    kafalah_guarantee: bool

    request: FinancingRequest

    @field_validator("monthly_revenue_sar")
    @classmethod
    def _non_negative(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("monthly revenue cannot be negative")
        return v

    # ---- Derived figures (deterministic, no model involved) ----

    @property
    def annual_revenue_sar(self) -> float:
        return sum(self.monthly_revenue_sar)

    @property
    def avg_monthly_revenue_sar(self) -> float:
        return mean(self.monthly_revenue_sar)

    @property
    def revenue_cv(self) -> float:
        """Coefficient of variation of monthly revenue (volatility)."""
        avg = self.avg_monthly_revenue_sar
        return pstdev(self.monthly_revenue_sar) / avg if avg > 0 else float("inf")

    @property
    def zero_revenue_months(self) -> int:
        return sum(1 for x in self.monthly_revenue_sar if x == 0)

    @property
    def overdue_receivables_ratio(self) -> float:
        if self.receivables_outstanding_sar == 0:
            return 0.0
        return self.receivables_overdue_90d_sar / self.receivables_outstanding_sar

    @property
    def cr_days_left(self) -> int:
        return (self.cr_expiry - self.as_of).days


class Finding(BaseModel):
    """The outcome of one rule for one business."""

    code: str
    passed: bool
    severity: Severity
    weight: float
    message: str
    evidence: dict[str, float | int | str | bool | None]
    source: str
    assumption: bool


class Assessment(BaseModel):
    business_id: str
    policy_id: str
    policy_version: str
    as_of: date
    score: float = Field(ge=0, le=100)
    ready: bool
    ready_threshold: float
    blockers: list[Finding]
    passed: list[Finding]
    metrics: dict[str, float | str | None]

    @property
    def blocker_codes(self) -> list[str]:
        return [b.code for b in self.blockers]
