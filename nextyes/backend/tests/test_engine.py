from __future__ import annotations

import pytest

from app.engine import FinancialSnapshot, assess, available_policies, load_policy
from app.engine import finance
from app.engine.rules import CHECKS

BANK = "commercial_bank_sme"
DIGITAL = "digital_lender_invoice"


def healthy(**overrides) -> FinancialSnapshot:
    """A business that passes every rule of both policies."""
    data = {
        "business_id": "t-healthy",
        "as_of": "2026-10-30",
        "cr_active": True,
        "cr_expiry": "2027-10-30",
        "operating_months": 48,
        "monthly_revenue_sar": [250_000] * 12,
        "operating_margin": 0.20,
        "existing_monthly_debt_service_sar": 5_000,
        "has_active_defaults": False,
        "receivables_outstanding_sar": 400_000,
        "receivables_overdue_90d_sar": 40_000,
        "einvoicing_compliant": True,
        "vat_filed_on_time": True,
        "financial_statements_available": True,
        "separate_business_account": True,
        "collateral_available": False,
        "kafalah_guarantee": True,
        "request": {"amount_sar": 500_000, "tenor_months": 60, "annual_profit_rate": 0.09},
    }
    data.update(overrides)
    return FinancialSnapshot.model_validate(data)


# ---------- finance math ----------

def test_installment_known_value():
    # 100,000 over 12 months at 12%/yr → 8,884.88 (standard annuity)
    assert finance.installment(100_000, 0.12, 12) == pytest.approx(8884.88, abs=0.01)


def test_installment_zero_rate():
    assert finance.installment(12_000, 0.0, 12) == 1000


@pytest.mark.parametrize("rate", [0.0, 0.05, 0.09, 0.15])
def test_principal_is_inverse_of_installment(rate):
    pay = finance.installment(750_000, rate, 60)
    assert finance.principal_for_installment(pay, rate, 60) == pytest.approx(750_000)


@pytest.mark.parametrize(
    "revenue, expected",
    [(2_000_000, "micro"), (3_000_000, "micro"), (10_000_000, "small"), (150_000_000, "medium"), (250_000_000, "not_sme")],
)
def test_size_class(revenue, expected):
    assert finance.size_class(revenue) == expected


# ---------- policies ----------

def test_both_policies_load_and_reference_real_checks():
    assert {BANK, DIGITAL} <= set(available_policies())
    for name in (BANK, DIGITAL):
        policy = load_policy(name)
        assert len(policy.version) == 12
        for rule in policy.rules:
            assert rule.check in CHECKS, f"{name}:{rule.id} uses unknown check {rule.check}"
            assert rule.source, f"{name}:{rule.id} has no source"


@pytest.mark.parametrize("name", [BANK, DIGITAL])
def test_healthy_business_is_ready(name):
    result = assess(healthy(), load_policy(name))
    assert result.blockers == []
    assert result.score == 100
    assert result.ready


# ---------- each blocker fires on its own ----------

@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"cr_active": False}, "CR_INVALID"),
        ({"cr_expiry": "2026-11-17"}, "CR_EXPIRING"),
        ({"operating_months": 18}, "HISTORY_SHORT"),
        ({"has_active_defaults": True}, "ACTIVE_DEFAULTS"),
        ({"request": {"amount_sar": 3_000_000, "tenor_months": 60, "annual_profit_rate": 0.09}}, "DSCR_LOW"),
        ({"monthly_revenue_sar": [100_000, 400_000] * 6}, "CASHFLOW_VOLATILE"),
        ({"einvoicing_compliant": False}, "EINVOICING"),
        ({"vat_filed_on_time": False}, "VAT_LATE"),
        ({"financial_statements_available": False}, "STATEMENTS_MISSING"),
        ({"separate_business_account": False}, "ACCOUNTS_MIXED"),
        ({"kafalah_guarantee": False}, "NO_SECURITY"),
        ({"receivables_overdue_90d_sar": 200_000}, "RECEIVABLES_OVERDUE"),
    ],
)
def test_single_blocker(overrides, code):
    result = assess(healthy(**overrides), load_policy(BANK))
    assert result.blocker_codes == [code]
    assert result.blockers[0].message  # message formats without KeyError


def test_expired_cr_is_reported_once():
    result = assess(healthy(cr_expiry="2026-10-01"), load_policy(BANK))
    assert result.blocker_codes == ["CR_INVALID"]


def test_hard_blocker_means_not_ready_even_with_high_score():
    result = assess(healthy(cr_expiry="2026-11-17"), load_policy(BANK))
    assert result.score > result.ready_threshold
    assert not result.ready


def test_soft_blockers_alone_can_still_be_ready():
    result = assess(healthy(vat_filed_on_time=False), load_policy(BANK))
    assert result.blocker_codes == ["VAT_LATE"]
    assert result.ready


def test_hard_blockers_listed_before_soft():
    result = assess(healthy(vat_filed_on_time=False, kafalah_guarantee=False), load_policy(BANK))
    assert result.blocker_codes == ["NO_SECURITY", "VAT_LATE"]


# ---------- the levers the agent will pull ----------

def test_resizing_to_max_affordable_clears_dscr():
    policy = load_policy(BANK)
    big = healthy(request={"amount_sar": 3_000_000, "tenor_months": 60, "annual_profit_rate": 0.09})
    cap = assess(big, policy).metrics["max_affordable_sar"]
    assert 0 < cap < 3_000_000
    resized = healthy(request={"amount_sar": cap, "tenor_months": 60, "annual_profit_rate": 0.09})
    assert "DSCR_LOW" not in assess(resized, policy).blocker_codes


def test_kafalah_guarantee_replaces_collateral():
    policy = load_policy(BANK)
    assert "NO_SECURITY" in assess(healthy(kafalah_guarantee=False), policy).blocker_codes
    assert "NO_SECURITY" not in assess(healthy(kafalah_guarantee=False, collateral_available=True), policy).blocker_codes


# ---------- robustness: the lender changes ----------

def test_policy_swap_changes_verdict_without_code_change():
    young = healthy(operating_months=18)
    assert "HISTORY_SHORT" in assess(young, load_policy(BANK)).blocker_codes
    assert "HISTORY_SHORT" not in assess(young, load_policy(DIGITAL)).blocker_codes


def test_digital_lender_minimum_revenue():
    small = healthy(monthly_revenue_sar=[150_000] * 12, request={"amount_sar": 200_000, "tenor_months": 36, "annual_profit_rate": 0.09})
    assert "REVENUE_LOW" in assess(small, load_policy(DIGITAL)).blocker_codes
    assert "REVENUE_LOW" not in [r.id for r in load_policy(BANK).rules]


# ---------- determinism ----------

def test_same_input_same_output():
    policy = load_policy(BANK)
    s = healthy(cr_expiry="2026-11-17", receivables_overdue_90d_sar=200_000)
    assert assess(s, policy) == assess(s, policy)


def test_demo_bakery_supplier():
    from pathlib import Path

    snap = FinancialSnapshot.model_validate_json(
        (Path(__file__).parents[1] / "examples" / "bakery_supplier.json").read_text()
    )
    result = assess(snap, load_policy(BANK))
    assert not result.ready
    assert set(result.blocker_codes) == {"CR_EXPIRING", "DSCR_LOW", "NO_SECURITY", "RECEIVABLES_OVERDUE"}
