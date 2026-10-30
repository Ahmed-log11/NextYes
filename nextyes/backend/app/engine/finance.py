"""Plain financing math. Pure functions, no I/O."""

from __future__ import annotations

from .models import FinancialSnapshot, SizeClass


def installment(principal: float, annual_rate: float, months: int) -> float:
    """Monthly payment of a fully amortising facility."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_rate / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def principal_for_installment(payment: float, annual_rate: float, months: int) -> float:
    """Inverse of `installment`: the largest principal a payment can service."""
    if payment <= 0:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return payment * months
    return payment * (1 - (1 + r) ** -months) / r


def monthly_operating_cash(s: FinancialSnapshot) -> float:
    """Cash available each month to service debt."""
    return s.avg_monthly_revenue_sar * s.operating_margin


def dscr(s: FinancialSnapshot) -> float:
    """Debt service coverage ratio including the requested facility."""
    new_payment = installment(
        s.request.amount_sar, s.request.annual_profit_rate, s.request.tenor_months
    )
    total = s.existing_monthly_debt_service_sar + new_payment
    return monthly_operating_cash(s) / total if total > 0 else float("inf")


def max_affordable_amount(s: FinancialSnapshot, min_dscr: float) -> float:
    """Largest request (same tenor and rate) that still meets `min_dscr`."""
    room = monthly_operating_cash(s) / min_dscr - s.existing_monthly_debt_service_sar
    return principal_for_installment(room, s.request.annual_profit_rate, s.request.tenor_months)


def size_class(annual_revenue_sar: float) -> SizeClass:
    """Monsha'at classification by annual revenue (SAR).

    Micro 0–3M, small 3–40M, medium 40–200M.
    Source: Qoyod SME financing report 2026, citing Monsha'at's unified definition.
    """
    if annual_revenue_sar <= 3_000_000:
        return "micro"
    if annual_revenue_sar <= 40_000_000:
        return "small"
    if annual_revenue_sar <= 200_000_000:
        return "medium"
    return "not_sme"
