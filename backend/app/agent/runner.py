"""Play a whole journey without a language model: assess, plan, act, let a month pass, repeat.

This is the agent's skeleton and the baseline for evaluation. The LangGraph journey
(graph.py, Chunk 4b) runs the same steps with real approval pauses and a model that
explains; this runner approves on a callback, so tests and evaluation can play
hundreds of journeys in seconds.

    python -m app.agent.runner demo-bakery-supplier
"""

from __future__ import annotations

import argparse
import json
from typing import Callable

from pydantic import BaseModel

from ..engine import FinancialSnapshot, assess, load_policy
from .models import PlanStep
from .planner import build_plan, validate_plan
from .simulator import advance_month, start_step

Approver = Callable[[PlanStep], bool]
MAX_JOURNEY_MONTHS = 12


class Checkpoint(BaseModel):
    month: int
    policy_id: str
    score: float
    ready: bool
    blockers: list[str]


class Trace(BaseModel):
    business_id: str
    start_policy: str
    final_policy: str
    outcome: str                  # ready | escalated (no remedy) | not_reachable (too long) | owner_declined | out_of_time
    months: int
    steps: list[PlanStep]
    checkpoints: list[Checkpoint]
    final_snapshot: FinancialSnapshot


def approve_all(step: PlanStep) -> bool:
    return True


def run_journey(s: FinancialSnapshot, policy_id: str, approve: Approver = approve_all,
                max_months: int = MAX_JOURNEY_MONTHS) -> Trace:
    start_policy, month, steps, checkpoints = policy_id, 0, [], []

    def check() -> bool:
        a = assess(s, load_policy(policy_id))
        checkpoints.append(Checkpoint(month=month, policy_id=policy_id, score=a.score, ready=a.ready,
                                      blockers=a.blocker_codes))
        return a.ready

    def finish(outcome: str) -> Trace:
        return Trace(business_id=s.business_id, start_policy=start_policy, final_policy=policy_id,
                     outcome=outcome, months=month, steps=steps, checkpoints=checkpoints, final_snapshot=s)

    while True:
        if check():
            return finish("ready")
        if month >= max_months:
            return finish("out_of_time")

        plan = build_plan(s, policy_id, steps, first_id=len(steps) + 1)
        issues = validate_plan(plan, s, steps)
        if issues:  # the deterministic planner must always pass its own validator
            raise RuntimeError(f"invalid plan for {s.business_id}: {issues}")

        for st in plan.steps:
            steps.append(st)
            if st.executor == "advisor":
                st.status = "in_progress"  # handed over; the journey stops below
            elif st.executor == "approve" and not approve(st):
                st.status = "declined"
            elif st.remedy == "SWITCH_LENDER":
                policy_id = st.params["policy_id"]
                st.status, st.started_month, st.done_month = "done", month, month
            else:
                s = start_step(s, st, month)

        if plan.estimated_months is None:
            # no lender reachable within the journey: hand over (no remedy) or tell the owner
            # when to come back (remedies exist but take longer than MAX_JOURNEY_MONTHS)
            check()
            if plan.declined:
                return finish("owner_declined")
            return finish("escalated" if plan.unfixable else "not_reachable")
        if check():  # immediate steps (resize, renew) may already be enough
            return finish("ready")
        checkpoints.pop()
        s = advance_month(s, steps, month, load_policy(policy_id))
        month += 1


def main() -> None:
    from ..synth.dataset import build

    ap = argparse.ArgumentParser()
    ap.add_argument("business_id")
    ap.add_argument("--policy", default="commercial_bank_sme")
    args = ap.parse_args()
    b = next(b for split in build().values() for b in split if b.meta.business_id == args.business_id)
    t = run_journey(b.snapshot, args.policy)
    print(f"{t.business_id}: {t.outcome} after {t.months} months, lender {t.final_policy}")
    for c in t.checkpoints:
        print(f"  month {c.month}: score {c.score} {'READY' if c.ready else ''} blockers {c.blockers}")
    for st in t.steps:
        print(f"  [{st.executor:<7}] {st.remedy:<22} {st.status:<12} {st.detail.en}")
    import sys
    if "--json" in sys.argv:
        print(json.dumps(t.model_dump(mode="json"), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
