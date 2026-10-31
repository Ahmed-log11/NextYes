"""Does the agent's own planning help? The agent planner against the rule planner, journey by journey.

    python -m app.agent.evaluate_planner --split dev --workers 4
    python -m app.agent.evaluate_planner --split dev --brain template   # offline sanity run, no model

Each business is played twice from its true data with the offline runner (runner.py),
once with the rule planner and once with the agent planner (agent_planner.py), in two
scenarios:
- approve_all: the owner approves every step the agent asks for;
- decline_one: the owner says no to the first step they are asked to approve
  (a common real case: "I don't want a guarantee", "I won't lower the amount").

Reported per scenario: outcomes (ready / owner_declined / escalated / ...), months to
ready, steps the owner had to approve or do, and for the agent planner how its proposals
fared: valid at once, valid after the validator's feedback, rejected (rules used), and
whether the simulator found it better than, equal to, or worse than the rule plan.
Answers are cached (cache/brain), so a second run is free and gives the same numbers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

from ..synth.dataset import build
from .agent_planner import make_plan
from .brain import ClaudeBrain, TemplateBrain
from .runner import rules_planner, run_journey

REPORTS = Path(__file__).resolve().parents[2] / "reports"
POLICY = "commercial_bank_sme"
SCENARIOS = ("approve_all", "decline_one")


def approver(scenario: str):
    said_no = []

    def approve(step) -> bool:
        if scenario == "decline_one" and not said_no and step.remedy != "SWITCH_LENDER":
            said_no.append(step.remedy)
            return False
        return True
    return approve, said_no


def play(b, scenario: str, planner: str, brain) -> dict:
    approve, said_no = approver(scenario)
    if planner == "rules":
        t = run_journey(b.snapshot, POLICY, approve=approve, plan_fn=rules_planner)
    else:
        t = run_journey(b.snapshot, POLICY, approve=approve,
                        plan_fn=lambda s, p, st, n, m: make_plan(s, p, st, n, brain=brain, month=m, planner="agent"))
    owner_steps = sum(st.executor in ("approve", "owner") and st.status != "declined" for st in t.steps)
    return {
        "outcome": t.outcome, "months": t.months if t.outcome == "ready" else None, "lender": t.final_policy,
        "owner_steps": owner_steps, "declined": said_no,
        "planning": [r.model_dump(mode="json") for r in t.planning],
    }


def verdict(r: dict) -> str | None:
    """How one planning round went for the agent."""
    if r["agent"] is None:
        if r["attempts"] == 0:
            return None  # nothing compared (nothing to plan)
        return "unavailable" if "unavailable" in r["why"] else "rejected"
    from .agent_planner import Projection
    ka, kb = Projection(**r["agent"]).key(), Projection(**r["rules"]).key()
    return "better" if ka < kb else "same" if ka == kb else "worse"


def summarise(rows: list[dict]) -> dict:
    out = {}
    for sc in SCENARIOS:
        part = {}
        for planner in ("rules", "agent"):
            runs = [r[sc][planner] for r in rows]
            ready = [x for x in runs if x["outcome"] == "ready"]
            part[planner] = {
                "outcomes": dict(Counter(x["outcome"] for x in runs)),
                "ready": len(ready), "journeys": len(runs),
                "mean_months_when_ready": round(mean(x["months"] for x in ready), 2) if ready else None,
                "mean_owner_steps": round(mean(x["owner_steps"] for x in runs), 2) if runs else None,
            }
        rounds = [p for r in rows for p in r[sc]["agent"]["planning"]]
        v = Counter(filter(None, (verdict(p) for p in rounds)))
        part["agent_rounds"] = {
            "compared": sum(v.values()), "verdicts": dict(v),
            "valid_first_try": sum(1 for p in rounds if p["agent"] is not None and p["attempts"] == 1),
            "valid_after_feedback": sum(1 for p in rounds if p["agent"] is not None and p["attempts"] == 2),
            "plan_used": sum(1 for p in rounds if p["source"] == "agent"),
        }
        # journeys where the two planners ended differently
        part["different_outcome"] = [
            {"business_id": r["business_id"], "rules": r[sc]["rules"]["outcome"], "agent": r[sc]["agent"]["outcome"],
             "agent_lender": r[sc]["agent"]["lender"]}
            for r in rows if r[sc]["rules"]["outcome"] != r[sc]["agent"]["outcome"]]
        out[sc] = part
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "heldout", "demo"])
    ap.add_argument("--brain", default="claude", choices=["claude", "template"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    businesses = build()[args.split]
    if args.limit:
        businesses = businesses[: args.limit]
    brain = ClaudeBrain() if args.brain == "claude" else TemplateBrain()

    def one(b):
        row = {"business_id": b.meta.business_id}
        for sc in SCENARIOS:
            row[sc] = {"rules": play(b, sc, "rules", brain), "agent": play(b, sc, "agent", brain)}
        print(f"  {row['business_id']}: " + " | ".join(
            f"{sc} rules={row[sc]['rules']['outcome']} agent={row[sc]['agent']['outcome']}" for sc in SCENARIOS), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        rows = list(ex.map(one, businesses))
    summary = summarise(rows)
    summary["usage"] = dict(getattr(brain, "usage", {}))
    REPORTS.mkdir(exist_ok=True)
    stem = REPORTS / f"planner-{args.split}-{args.brain}"
    stem.with_suffix(".json").write_text(json.dumps({"split": args.split, "brain": args.brain, "summary": summary,
                                                     "journeys": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Agent planner vs rule planner: {args.split} ({len(rows)} businesses, brain {args.brain})", ""]
    for sc in SCENARIOS:
        s = summary[sc]
        lines += [f"## {sc}", "", "| | rules | agent |", "|---|---|---|",
                  f"| ready | {s['rules']['ready']}/{s['rules']['journeys']} | {s['agent']['ready']}/{s['agent']['journeys']} |",
                  f"| mean months when ready | {s['rules']['mean_months_when_ready']} | {s['agent']['mean_months_when_ready']} |",
                  f"| mean owner steps | {s['rules']['mean_owner_steps']} | {s['agent']['mean_owner_steps']} |",
                  f"| outcomes | {s['rules']['outcomes']} | {s['agent']['outcomes']} |", "",
                  f"Agent planning rounds: {s['agent_rounds']}", "",
                  f"Different outcome: {len(s['different_outcome'])} journeys", ""]
        lines += [f"- {d['business_id']}: rules {d['rules']}, agent {d['agent']} ({d['agent_lender']})"
                  for d in s["different_outcome"]] + [""]
    stem.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"usage: {summary['usage']}")


if __name__ == "__main__":
    main()
