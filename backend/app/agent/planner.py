"""Turn an assessment into a plan, and check any plan before it is used.

`build_plan` is deterministic: for each blocker it picks the first applicable remedy
from the catalog, and it chooses the lender the business can be ready for soonest.
It is the baseline the language-model planner (Chunk 4c) is compared against, and
its fallback.

`validate_plan` checks ANY plan, including one written by a model: every hard
blocker covered, only known and allowed remedies, the right executor for each step,
and a resized amount the engine agrees the business can repay. A plan with any
issue is rejected.
"""

from __future__ import annotations

from ..engine import FinancialSnapshot, Policy, assess, available_policies, finance, load_policy
from .models import Plan, PlanIssue, PlanStep, Text
from .remedies import CATALOG, ESCALATE, FORBIDDEN, MAX_MONTHS, MIN_USEFUL_AMOUNT, Remedy, remedies_for, rule_params

OPEN = ("proposed", "awaiting_approval", "in_progress")  # steps that still count as covering a blocker
ORDER = {"approve": 0, "agent": 1, "owner": 2, "wait": 3, "advisor": 4}


def _choose(code: str, s: FinancialSnapshot, p: Policy) -> Remedy | None:
    return next((r for r in remedies_for(code) if r.applicable(s, p)), None)


def estimate(s: FinancialSnapshot, p: Policy) -> tuple[int | None, list[str]]:
    """Months until ready for this lender with known remedies (None if not reachable),
    and the hard blockers no remedy covers."""
    a = assess(s, p)
    total = sum(f.weight for f in a.blockers + a.passed)
    earned = sum(f.weight for f in a.passed)
    months, unfixable, soft = 0, [], []
    for b in a.blockers:
        r = _choose(b.code, s, p)
        if b.severity == "hard":
            if r is None:
                unfixable.append(b.code)
                continue
            months = max(months, r.duration(s, p, r.params(s, p)))
            earned += b.weight
        elif r is not None:
            soft.append((r.duration(s, p, r.params(s, p)), b.weight))
    # soft blockers count only as far as the score needs them, quickest first
    for dur, w in sorted(soft):
        if 100 * earned / total >= p.ready_threshold:
            break
        months, earned = max(months, dur), earned + w
    if unfixable or months > MAX_MONTHS or 100 * earned / total < p.ready_threshold:
        return None, unfixable
    return months, []


def match_funder(s: FinancialSnapshot, current: str, allow_switch: bool = True) -> tuple[str, dict[str, int | None]]:
    """The lender the business can be ready for soonest; the current one wins ties."""
    est = {pid: estimate(s, load_policy(pid))[0] for pid in available_policies()}
    if not allow_switch:
        return current, est
    reachable = {pid: m for pid, m in est.items() if m is not None}
    if not reachable or est.get(current) is not None and est[current] == min(reachable.values()):
        return current, est
    return min(reachable, key=lambda pid: (reachable[pid], pid != current)), est


def _step(step_id: str, r: Remedy, codes: list[str], s: FinancialSnapshot, p: Policy, params=None) -> PlanStep:
    prm = params if params is not None else r.params(s, p)
    return PlanStep(step_id=step_id, remedy=r.id, fixes=codes, executor=r.executor, title=r.title,
                    detail=r.detail(s, p, prm), params=prm, duration_months=r.duration(s, p, prm))


def build_plan(s: FinancialSnapshot, current_policy: str, existing: list[PlanStep] | None = None,
               first_id: int = 1) -> Plan:
    """Steps for the blockers not already covered by an open step in `existing`."""
    existing = existing or []
    # one switch per journey at most, and never again after the owner said no to one
    switched = any(st.remedy == "SWITCH_LENDER" for st in existing)
    target, est = match_funder(s, current_policy, allow_switch=not switched)
    p = load_policy(target)
    steps: list[PlanStep] = []
    n = first_id

    if target != current_policy:
        cur = load_policy(current_policy)
        months, before = est[target], est[current_policy]
        soon_en = "now" if months == 0 else f"in about {months} month{'s' if months > 1 else ''}"
        soon_ar = "الآن" if months == 0 else f"خلال نحو {months} {'شهر' if months == 1 else 'أشهر'}"
        if before is None:
            reason_en = f"ready {soon_en}; the current lender is out of reach within {MAX_MONTHS} months"
            reason_ar = f"جاهزة {soon_ar}؛ والممول الحالي غير ممكن خلال {MAX_MONTHS} شهرًا"
        else:
            reason_en, reason_ar = f"ready {soon_en} instead of {before} months", f"جاهزة {soon_ar} بدلًا من {before} أشهر"
        params = {"policy_id": target, "from_policy": current_policy,
                  "to_name_en": p.name, "to_name_ar": p.name_ar or p.name,
                  "from_name_en": cur.name, "from_name_ar": cur.name_ar or cur.name,
                  "reason_en": reason_en, "reason_ar": reason_ar}
        steps.append(_step(f"s{n}", CATALOG["SWITCH_LENDER"], [], s, p, params))
        n += 1

    covered = {c for st in existing if st.status in OPEN for c in st.fixes}
    refused = {st.remedy for st in existing if st.status == "declined"}  # never re-proposed
    unfixable: list[str] = []
    declined: list[str] = []
    by_remedy: dict[str, list[str]] = {}
    for b in assess(s, p).blockers:
        if b.code in covered:
            continue
        r = _choose(b.code, s, p)
        if r is not None and r.id in refused:
            if b.severity == "hard":
                declined.append(b.code)
            continue
        if r is None:
            if b.severity == "hard":
                unfixable.append(b.code)
            continue
        by_remedy.setdefault(r.id, []).append(b.code)  # one step even if it fixes two blockers

    for rid, codes in by_remedy.items():
        steps.append(_step(f"s{n}", CATALOG[rid], codes, s, p))
        n += 1
    for code in unfixable:
        steps.append(PlanStep(step_id=f"s{n}", remedy="ESCALATE", fixes=[code], executor="advisor",
                              title=Text(en="Refer to a human advisor", ar="إحالة إلى مستشار"),
                              detail=ESCALATE.get(code, Text(en=f"No known remedy for {code}.",
                                                             ar=f"لا يوجد حل معروف لـ {code}."))))
        n += 1

    steps.sort(key=lambda st: (ORDER[st.executor], st.duration_months))
    months = None if declined else est[target]
    return Plan(policy_id=target, steps=steps, estimated_months=months, unfixable=unfixable, declined=declined)


def validate_plan(plan: Plan, s: FinancialSnapshot, existing: list[PlanStep] | None = None) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    if plan.policy_id not in available_policies():
        return [PlanIssue(code="UNKNOWN_LENDER", message=f"No lender policy {plan.policy_id}")]
    p = load_policy(plan.policy_id)

    for st in plan.steps:
        if st.remedy in FORBIDDEN:
            issues.append(PlanIssue(code="FORBIDDEN_STEP", message=f"{st.step_id}: {FORBIDDEN[st.remedy]}"))
            continue
        if st.remedy == "ESCALATE":
            continue
        r = CATALOG.get(st.remedy)
        if r is None:
            issues.append(PlanIssue(code="UNKNOWN_REMEDY", message=f"{st.step_id}: {st.remedy}"))
            continue
        if st.executor != r.executor:
            issues.append(PlanIssue(code="WRONG_EXECUTOR",
                                    message=f"{st.step_id}: {st.remedy} is done by {r.executor}, not {st.executor}"))
        if not set(st.fixes) <= set(r.fixes):
            issues.append(PlanIssue(code="WRONG_FIX", message=f"{st.step_id}: {st.remedy} cannot fix {st.fixes}"))
        if st.remedy == "RESIZE_REQUEST":
            min_dscr = (rule_params(p, "dscr_min") or {"min_dscr": 1.2})["min_dscr"]
            cap = finance.max_affordable_amount(s, min_dscr)
            amt = st.params.get("amount_sar", 0)
            if not MIN_USEFUL_AMOUNT <= amt <= cap:
                issues.append(PlanIssue(code="UNAFFORDABLE_AMOUNT",
                                        message=f"{st.step_id}: SAR {amt:,.0f} is outside SAR {MIN_USEFUL_AMOUNT:,}–{cap:,.0f}"))
        if st.remedy == "SWITCH_LENDER" and st.params.get("policy_id") != plan.policy_id:
            issues.append(PlanIssue(code="SWITCH_MISMATCH", message=f"{st.step_id}: switches to another lender than the plan's"))

    covered = {c for st in plan.steps + (existing or []) if st.status in OPEN for c in st.fixes}
    covered |= set(plan.declined)  # the owner said no: reported, not silently dropped
    for b in assess(s, p).blockers:
        if b.severity == "hard" and b.code not in covered:
            issues.append(PlanIssue(code="UNCOVERED_BLOCKER", message=f"{b.code} has no step"))
    return issues
