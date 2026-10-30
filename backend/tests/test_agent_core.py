"""The agent's deterministic core: remedies, simulator, planner, validator, journeys.

Uses dev and demo businesses only; held-out is kept for final numbers.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.agent.models import PlanStep, Text
from app.agent.planner import build_plan, estimate, match_funder, validate_plan
from app.agent.remedies import CATALOG, ESCALATE, FORBIDDEN
from app.agent.runner import run_journey
from app.agent.simulator import advance_month, pass_time, start_step
from app.engine import assess, available_policies, load_policy
from app.synth.dataset import build
from app.synth.generator import make_business

DATA = build()
DEV = DATA["dev"] + DATA["demo"]
POLICIES = available_policies()
BANK = "commercial_bank_sme"


def _demo(bid):
    return next(b for b in DATA["demo"] if b.meta.business_id == bid).snapshot


# --- catalog -----------------------------------------------------------------


def test_every_rule_has_a_remedy_or_an_escalation():
    for pid in POLICIES:
        for r in load_policy(pid).rules:
            assert any(r.id in rem.fixes for rem in CATALOG.values()) or r.id in ESCALATE, r.id


def test_every_remedy_speaks_both_languages():
    s, p = _demo("demo-bakery-supplier"), load_policy(BANK)
    for rem in CATALOG.values():
        assert rem.title.en and rem.title.ar
        if rem.id == "SWITCH_LENDER":
            continue  # its text needs both lenders; checked in the journey test below
        d = rem.detail(s, p, rem.params(s, p))
        assert d.en and d.ar


# --- remedy effects ----------------------------------------------------------


def _start(s, remedy_id, policy=BANK, month=0):
    p = load_policy(policy)
    r = CATALOG[remedy_id]
    prm = r.params(s, p)
    st = PlanStep(step_id="t", remedy=remedy_id, fixes=list(r.fixes), executor=r.executor, title=r.title,
                  detail=r.detail(s, p, prm), params=prm, duration_months=r.duration(s, p, prm))
    return start_step(s, st, month), st


def test_resizing_makes_the_request_repayable_at_once():
    s = _demo("demo-bakery-supplier")
    assert "DSCR_LOW" in assess(s, load_policy(BANK)).blocker_codes
    s2, st = _start(s, "RESIZE_REQUEST")
    assert st.status == "done" and "DSCR_LOW" not in assess(s2, load_policy(BANK)).blocker_codes


def test_kafalah_takes_effect_after_a_month():
    s = _demo("demo-bakery-supplier")
    s1, st = _start(s, "ADD_KAFALAH")
    assert st.status == "in_progress" and not s1.kafalah_guarantee
    s2 = advance_month(s1, [st], 0, load_policy(BANK))
    assert st.status == "done" and s2.kafalah_guarantee


def test_chasing_collects_until_within_the_limit():
    s = _demo("demo-bakery-supplier")
    before = s.overdue_receivables_ratio
    s1, st = _start(s, "CHASE_RECEIVABLES")
    s2 = advance_month(s1, [st], 0, load_policy(BANK))
    assert s2.receivables_overdue_90d_sar == pytest.approx(s.receivables_overdue_90d_sar / 2)
    assert s2.overdue_receivables_ratio < before
    assert st.status == "done"  # one month was enough for this business (44% -> 28%, limit 30%)


def test_steady_revenue_lowers_variation_month_by_month():
    s = _demo("demo-online-store")
    s1, st = _start(s, "STEADY_REVENUE", "digital_lender_invoice")
    cvs = [s1.revenue_cv]
    for m in range(4):
        s1 = advance_month(s1, [st], m, load_policy("digital_lender_invoice"))
        cvs.append(s1.revenue_cv)
    assert cvs == sorted(cvs, reverse=True) and cvs[-1] < cvs[0]


def test_time_passes_for_everyone():
    s = _demo("demo-contractor")
    s1 = pass_time(s, steady_revenue=False)
    assert s1.as_of.month == (s.as_of.month % 12) + 1 and s1.operating_months == s.operating_months + 1
    assert s1.monthly_revenue_sar == s.monthly_revenue_sar[1:] + [s.monthly_revenue_sar[0]]  # seasonality repeats


# --- planner and validator ---------------------------------------------------


@pytest.mark.parametrize("pid", POLICIES)
def test_deterministic_plans_always_pass_the_validator(pid):
    for b in DEV:
        plan = build_plan(b.snapshot, pid)
        assert validate_plan(plan, b.snapshot) == [], b.meta.business_id


def _plan():
    s = _demo("demo-bakery-supplier")
    return s, build_plan(s, BANK)


def test_validator_rejects_a_forbidden_step():
    s, plan = _plan()
    plan.steps.append(PlanStep(step_id="x", remedy="HIDE_DEBT", fixes=[], executor="agent",
                               title=Text(en="x", ar="x"), detail=Text(en="x", ar="x")))
    assert "FORBIDDEN_STEP" in {i.code for i in validate_plan(plan, s)}
    assert "HIDE_DEBT" in FORBIDDEN


def test_validator_rejects_a_plan_that_leaves_a_blocker_uncovered():
    s, plan = _plan()
    plan.steps = [st for st in plan.steps if st.remedy != "ADD_KAFALAH"]
    assert any(i.code == "UNCOVERED_BLOCKER" and "NO_SECURITY" in i.message for i in validate_plan(plan, s))


def test_validator_rejects_an_amount_the_business_cannot_repay():
    s, plan = _plan()
    resize = next(st for st in plan.steps if st.remedy == "RESIZE_REQUEST")
    resize.params["amount_sar"] = s.request.amount_sar  # "resize" to the original, unaffordable amount
    assert "UNAFFORDABLE_AMOUNT" in {i.code for i in validate_plan(plan, s)}


def test_validator_rejects_the_wrong_executor():
    s, plan = _plan()
    next(st for st in plan.steps if st.remedy == "CHASE_RECEIVABLES").executor = "owner"
    assert "WRONG_EXECUTOR" in {i.code for i in validate_plan(plan, s)}


def test_lender_is_switched_when_another_fits_sooner():
    s = _demo("demo-online-store")  # 1 year of history: too young for the bank, fine for the digital lender
    target, est = match_funder(s, BANK)
    assert target == "digital_lender_invoice" and est[target] < (est[BANK] or 99)
    assert build_plan(s, BANK).steps[0].remedy == "SWITCH_LENDER"


# --- whole journeys ----------------------------------------------------------


@pytest.mark.parametrize("pid", POLICIES)
def test_every_dev_business_reaches_ready(pid):
    for b in DEV:
        t = run_journey(b.snapshot, pid)
        assert t.outcome == "ready", (b.meta.business_id, t.checkpoints[-1].blockers)
        assert sum(st.remedy == "SWITCH_LENDER" for st in t.steps) <= 1
        assert assess(t.final_snapshot, load_policy(t.final_policy)).ready
        for st in t.steps:
            assert st.title.ar and st.detail.ar  # everything the owner sees exists in Arabic


def test_journeys_are_deterministic():
    s = _demo("demo-bakery-supplier")
    assert run_journey(s, BANK) == run_journey(s, BANK)


def test_a_declined_step_is_not_proposed_again():
    s = _demo("demo-bakery-supplier")
    t = run_journey(s, BANK, approve=lambda st: st.remedy != "RESIZE_REQUEST")
    assert t.outcome == "owner_declined"
    assert sum(st.remedy == "RESIZE_REQUEST" for st in t.steps) == 1


def test_no_reachable_lender_ends_the_journey_honestly():
    # built here, not taken from held-out: 8 months old and too small for the digital lender
    b = make_business("unit-young", 77000, ["HISTORY_SHORT", "REVENUE_LOW"])
    assert b.snapshot.operating_months < 12
    assert all(estimate(b.snapshot, load_policy(p))[0] is None for p in POLICIES)
    t = run_journey(b.snapshot, BANK)
    assert t.outcome == "not_reachable" and t.months == 0


def test_a_registration_that_runs_out_during_the_journey_is_caught():
    s = _demo("demo-bakery-supplier")  # its journey takes a month (Kafalah)
    s = s.model_copy(update={"cr_expiry": s.as_of + timedelta(days=95)})  # bank needs 90 days: fine today
    assert "CR_EXPIRING" not in assess(s, load_policy(BANK)).blocker_codes
    t = run_journey(s, BANK)
    renew = next(st for st in t.steps if st.remedy == "RENEW_CR")
    assert renew.started_month == 1 and t.outcome == "ready"  # spotted and fixed a month in
