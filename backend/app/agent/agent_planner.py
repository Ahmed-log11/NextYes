"""The agent plans; Python checks the plan and the simulator judges it.

Every time a plan is needed, two plans are made for the same situation:
- the agent's own plan: the language model (Sonnet) sees the lender's reasons, the
  evidence, every lender it could apply to and the remedies it may use (as a menu of
  tools with their effects), and proposes steps, an amount and a lender;
- the rule baseline: `planner.build_plan`, the fixed first-applicable-remedy planner.

The agent's plan must pass `validate_plan` (known remedies only, nothing forbidden or
already declined by the owner, every hard blocker covered, an amount the engine agrees
is affordable). If it fails, the issues go back to the model once to fix.

Then both plans are played forward with the month simulator, assuming the owner approves
what is asked. The better outcome wins: reaches the lender's threshold, then sooner, then
fewer steps the owner has to do or approve, then a higher final score (margin). On a tie the agent's plan is used (it is valid
and just as good). The model never decides readiness or the lender's verdict: the engine
does, before and after.

Each choice is returned as a report and written to the audit log, so the owner, the bank
and the evaluation can see whose plan ran and why.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from ..engine import FinancialSnapshot, assess, available_policies, finance, load_policy
from .models import Plan, PlanIssue, PlanStep, Text
from .planner import ORDER, _step, build_plan, estimate, switch_step, validate_plan
from .remedies import CATALOG, ESCALATE, MAX_MONTHS, remedies_for, rule_params
from .simulator import advance_month, start_step

PLANNER = os.environ.get("NEXTYES_PLANNER", "agent")  # agent | rules


class Projection(BaseModel):
    ready: bool
    months: int | None          # months until ready (None: not within MAX_MONTHS)
    score: float                # score at the end of the projection
    owner_actions: int          # steps the owner must approve or do
    steps: int

    def key(self) -> tuple:
        # agent-run steps cost the owner nothing, so a higher final score (more margin for the
        # lender's own check) beats a shorter plan
        return (not self.ready, self.months if self.months is not None else 99, self.owner_actions,
                -round(self.score, 1), self.steps)


class PlanningReport(BaseModel):
    source: str                         # agent | rules
    why: str                            # one line: why this plan was used
    agent: Projection | None = None
    rules: Projection | None = None
    agent_issues: list[str] = []        # validator issues on the agent's last proposal
    attempts: int = 0                   # model calls made for this plan
    reasoning: str | None = None        # the agent's own explanation of its plan


# ---------------------------------------------------------------- what the agent is told


def planning_brief(s: FinancialSnapshot, current_policy: str, existing: list[PlanStep]) -> dict[str, Any]:
    """The situation as data: every lender, its open reasons with evidence, and the menu
    of remedies with who does them and how long they take."""
    switched = any(st.remedy == "SWITCH_LENDER" for st in existing)
    refused = sorted({st.remedy for st in existing if st.status == "declined"})
    open_steps = [{"remedy": st.remedy, "fixes": st.fixes, "status": st.status}
                  for st in existing if st.status in ("awaiting_approval", "in_progress")]
    lenders = []
    for pid in available_policies():
        if switched and pid != current_policy:
            continue
        p = load_policy(pid)
        a = assess(s, p)
        min_dscr = (rule_params(p, "dscr_min") or {"min_dscr": 1.2})["min_dscr"]
        menu = {}
        for b in a.blockers:
            for r in remedies_for(b.code):
                if r.id in menu or not r.applicable(s, p):
                    continue
                prm = r.params(s, p)
                menu[r.id] = {"fixes": list(r.fixes), "executor": r.executor, "title": r.title.en,
                              "effect": r.detail(s, p, prm).en, "months": r.duration(s, p, prm),
                              **({"max_amount_sar": round(finance.max_affordable_amount(s, min_dscr))}
                                 if r.id == "RESIZE_REQUEST" else {})}
        lenders.append({
            "lender": pid, "name": p.name, "current": pid == current_policy,
            "score": a.score, "threshold": p.ready_threshold, "ready": a.ready,
            "reasons": [{"code": b.code, "severity": b.severity, "weight": b.weight, "message": b.message,
                         "evidence": b.evidence} for b in a.blockers],
            "remedies": menu,
        })
    return {
        "requested_amount_sar": s.request.amount_sar, "tenor_months": s.request.tenor_months,
        "lenders": lenders, "can_switch_lender": not switched,
        "already_running": open_steps, "declined_by_owner": refused,
        "max_months": MAX_MONTHS,
    }


PLAN_SYSTEM = """You are the planning step of NextYes, an agent that gets a small business in Saudi Arabia ready for financing.
You get the business's situation as JSON: each lender it could apply to, that lender's open reasons (hard = must be fixed,
soft = lowers the score; the score is the share of rule weight passed), and the remedies available for those reasons
(who does each one: agent = you do it, approve = the owner approves with one click, owner = the owner must do it,
wait = only time fixes it; and how many months it takes).
Choose ONE lender and the remedies that get the business to that lender's threshold soonest, with as few steps for the
owner as possible. Every hard reason of the chosen lender must be covered, either by a step or by a step already running.
Soft reasons only need a step if the score needs it. Use only remedies listed for the chosen lender; never one the owner
declined. For RESIZE_REQUEST give amount_sar, at most max_amount_sar and close to it (lower is safe, higher is rejected).
Switching lender is allowed at most once per journey and only if can_switch_lender is true.
You never decide approval: a rule engine checks your plan and a simulator compares it with a rule-based plan."""

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the plan: the lender to apply to and the steps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "lender": {"type": "string", "description": "lender id from the JSON"},
            "steps": {"type": "array", "items": {
                "type": "object",
                "properties": {"remedy": {"type": "string"},
                               "fixes": {"type": "array", "items": {"type": "string"}},
                               "amount_sar": {"type": "number", "description": "only for RESIZE_REQUEST"}},
                "required": ["remedy", "fixes"]}},
            "reasoning": {"type": "string", "description": "two sentences for the owner: why this plan"},
        },
        "required": ["lender", "steps", "reasoning"],
    },
}


# ---------------------------------------------------------------- the agent's plan as a Plan


def plan_from_proposal(d: dict[str, Any], s: FinancialSnapshot, current_policy: str,
                       existing: list[PlanStep], first_id: int) -> Plan:
    target = d.get("lender") if d.get("lender") in available_policies() else current_policy
    p = load_policy(target)
    steps: list[PlanStep] = []
    n = first_id
    if target != current_policy:
        est = {pid: estimate(s, load_policy(pid))[0] for pid in available_policies()}
        steps.append(switch_step(f"s{n}", s, current_policy, target, est))
        n += 1
    seen = set()
    for item in d.get("steps") or []:
        rid = str(item.get("remedy", "")).upper()
        if rid == "SWITCH_LENDER" or rid in seen:
            continue
        seen.add(rid)
        r = CATALOG.get(rid)
        if r is None:  # unknown: keep it so the validator reports it
            steps.append(PlanStep(step_id=f"s{n}", remedy=rid, fixes=list(item.get("fixes") or []), executor="agent",
                                  title=Text(en=rid, ar=rid), detail=Text(en="", ar="")))
            n += 1
            continue
        prm = r.params(s, p)
        if rid == "RESIZE_REQUEST" and item.get("amount_sar"):
            prm = {**prm, "amount_sar": float(item["amount_sar"])}
        fixes = [c for c in (item.get("fixes") or []) if isinstance(c, str)] or list(r.fixes)
        steps.append(_step(f"s{n}", r, fixes, s, p, prm))
        n += 1
    # hard reasons nothing can fix still go to an advisor, exactly as in the rule plan
    covered = {c for st in steps for c in st.fixes} | {c for st in existing
                                                       if st.status in ("awaiting_approval", "in_progress")
                                                       for c in st.fixes}
    refused = {st.remedy for st in existing if st.status == "declined"}
    unfixable, declined = [], []
    for b in assess(s, p).blockers:
        if b.severity != "hard" or b.code in covered:
            continue
        options = [r for r in remedies_for(b.code) if r.applicable(s, p)]
        if not options:
            unfixable.append(b.code)
            steps.append(PlanStep(step_id=f"s{n}", remedy="ESCALATE", fixes=[b.code], executor="advisor",
                                  title=Text(en="Refer to a human advisor", ar="إحالة إلى مستشار"),
                                  detail=ESCALATE.get(b.code, Text(en=f"No known remedy for {b.code}.",
                                                                   ar=f"لا يوجد حل معروف لـ {b.code}."))))
            n += 1
        elif all(r.id in refused for r in options):
            declined.append(b.code)
    steps.sort(key=lambda st: (ORDER.get(st.executor, 9), st.duration_months))
    return Plan(policy_id=target, steps=steps, estimated_months=None, unfixable=unfixable, declined=declined)


# ---------------------------------------------------------------- judging a plan


def project(s: FinancialSnapshot, plan: Plan, existing: list[PlanStep], month: int = 0) -> Projection:
    """Play the plan forward (owner approves everything it asks) until ready or MAX_MONTHS."""
    steps = [st.model_copy(deep=True) for st in existing]
    for st in steps:  # steps waiting for approval are assumed approved too
        if st.status == "awaiting_approval":
            s = start_step(s, st, month)
    policy_id = plan.policy_id
    owner_actions = 0
    new = [st.model_copy(deep=True) for st in plan.steps]
    for st in new:
        steps.append(st)
        if st.executor in ("approve", "owner"):
            owner_actions += 1
        if st.remedy == "SWITCH_LENDER":
            st.status = "done"
        elif st.executor == "advisor" or st.remedy not in CATALOG:
            st.status = "in_progress"
        else:
            s = start_step(s, st, month)
    p = load_policy(policy_id)
    blocked = bool(plan.unfixable or plan.declined)
    for k in range(MAX_MONTHS + 1):
        a = assess(s, p)
        if a.ready and not blocked:
            return Projection(ready=True, months=k, score=a.score, owner_actions=owner_actions, steps=len(new))
        if k == MAX_MONTHS:
            break
        s = advance_month(s, steps, month + k, p)
    return Projection(ready=False, months=None, score=assess(s, p).score, owner_actions=owner_actions, steps=len(new))


def make_plan(s: FinancialSnapshot, current_policy: str, existing: list[PlanStep], first_id: int,
              brain: Any = None, month: int = 0, planner: str | None = None) -> tuple[Plan, PlanningReport]:
    """The plan to act on, and the report of how it was chosen."""
    rules = build_plan(s, current_policy, existing, first_id=first_id)
    nothing_to_plan = not rules.steps and not rules.declined and not rules.unfixable
    mode = planner or PLANNER
    propose = getattr(brain, "propose_plan", None)
    if nothing_to_plan or mode != "agent" or propose is None:
        why = "nothing new to plan" if nothing_to_plan else "the rule planner is configured"
        return rules, PlanningReport(source="rules", why=why)

    rules_proj = project(s, rules, existing, month)
    brief = planning_brief(s, current_policy, existing)
    report = PlanningReport(source="rules", why="", rules=rules_proj)
    feedback: list[PlanIssue] = []
    agent_plan = None
    for attempt in range(2):
        d = propose(brief, [i.message for i in feedback])
        report.attempts = attempt + 1
        if not d:
            report.why = "the model was unavailable; the rule plan was used"
            return rules, report
        cand = plan_from_proposal(d, s, current_policy, existing, first_id)
        feedback = validate_plan(cand, s, existing)
        report.reasoning = str(d.get("reasoning") or "")[:600]
        if not feedback:
            agent_plan = cand
            break
    report.agent_issues = [i.message for i in feedback]
    if agent_plan is None:
        report.why = "the agent's plan failed validation twice; the rule plan was used"
        return rules, report

    agent_proj = project(s, agent_plan, existing, month)
    report.agent = agent_proj
    if agent_proj.ready and agent_proj.key() <= rules_proj.key():
        agent_plan.estimated_months = agent_proj.months
        report.source = "agent"
        report.why = ("the agent's plan projects a better outcome than the rule plan"
                      if agent_proj.key() < rules_proj.key()
                      else "the agent's plan is valid and projects the same outcome as the rule plan")
        return agent_plan, report
    report.why = ("neither plan reaches the threshold; the rule plan was kept" if not agent_proj.ready and not rules_proj.ready
                  else "the rule plan projects a better outcome than the agent's plan")
    return rules, report


def describe(report: PlanningReport) -> Text:
    """One audit-log line about the choice."""
    def p(x: Projection | None) -> str:
        if x is None:
            return "n/a"
        return (f"ready in {x.months} month(s), {x.owner_actions} owner action(s)" if x.ready
                else f"not ready within {MAX_MONTHS} months")

    def p_ar(x: Projection | None) -> str:
        if x is None:
            return "غير متاح"
        return (f"جاهزة خلال {x.months} شهر، و{x.owner_actions} إجراء من المالك" if x.ready
                else f"غير جاهزة خلال {MAX_MONTHS} شهرًا")

    who = "The agent's plan" if report.source == "agent" else "The rule plan"
    who_ar = "خطة الوكيل" if report.source == "agent" else "الخطة المبنية على القواعد"
    if report.agent is None and report.rules is None:
        return Text(en=f"{who} was used ({report.why}).", ar=f"استُخدمت {who_ar}.")
    return Text(
        en=f"{who} was used: {report.why}. Agent: {p(report.agent)}; rules: {p(report.rules)}.",
        ar=f"استُخدمت {who_ar}. خطة الوكيل: {p_ar(report.agent)}؛ خطة القواعد: {p_ar(report.rules)}.")
