"""The agent's own planning: validated by Python, judged against the rule plan by the simulator.

A scripted brain stands in for the model, so these run offline and say exactly what
happens for a good, a bad and a fixable proposal.
"""

from app.agent.agent_planner import make_plan, planning_brief, project
from app.agent.planner import build_plan
from app.agent.runner import run_journey
from app.agent.service import find_business

POLICY = "commercial_bank_sme"


def bakery():
    _, b, _ = find_business("demo-bakery-supplier")
    return b.snapshot


class Scripted:
    """Returns the given proposals in order, records what it was told."""

    def __init__(self, *proposals):
        self.proposals = list(proposals)
        self.seen = []

    def propose_plan(self, brief, feedback):
        self.seen.append({"declined": brief["declined_by_owner"], "feedback": feedback})
        return self.proposals.pop(0) if self.proposals else None


SAME_AS_RULES = {"lender": POLICY, "reasoning": "fix every reason", "steps": [
    {"remedy": "RESIZE_REQUEST", "fixes": ["DSCR_LOW"], "amount_sar": 1_450_000},
    {"remedy": "RENEW_CR", "fixes": ["CR_EXPIRING"]},
    {"remedy": "ADD_KAFALAH", "fixes": ["NO_SECURITY"]},
    {"remedy": "CHASE_RECEIVABLES", "fixes": ["RECEIVABLES_OVERDUE"]}]}


def test_brief_lists_every_lender_with_reasons_and_remedies():
    brief = planning_brief(bakery(), POLICY, [])
    ids = {l["lender"] for l in brief["lenders"]}
    assert ids == {"commercial_bank_sme", "digital_lender_invoice"}
    cur = next(l for l in brief["lenders"] if l["current"])
    assert {r["code"] for r in cur["reasons"]} >= {"DSCR_LOW", "NO_SECURITY"}
    assert cur["remedies"]["RESIZE_REQUEST"]["max_amount_sar"] > 1_000_000


def test_projection_of_the_rule_plan_reaches_ready():
    s = bakery()
    pr = project(s, build_plan(s, POLICY, []), [])
    assert pr.ready and pr.months == 1


def test_valid_proposal_as_good_as_rules_is_used():
    plan, rep = make_plan(bakery(), POLICY, [], 1, brain=Scripted(SAME_AS_RULES), planner="agent")
    assert rep.source == "agent" and rep.attempts == 1
    assert rep.agent.key() == rep.rules.key()
    assert {st.remedy for st in plan.steps} == {"RESIZE_REQUEST", "RENEW_CR", "ADD_KAFALAH", "CHASE_RECEIVABLES"}


def test_unaffordable_amount_is_rejected_then_rules_win():
    bad = {**SAME_AS_RULES, "steps": [{**SAME_AS_RULES["steps"][0], "amount_sar": 2_400_000}] + SAME_AS_RULES["steps"][1:]}
    brain = Scripted(bad, bad)
    plan, rep = make_plan(bakery(), POLICY, [], 1, brain=brain, planner="agent")
    assert rep.source == "rules" and rep.attempts == 2
    assert any("outside" in i for i in rep.agent_issues)
    assert brain.seen[1]["feedback"], "the second attempt must be told what was wrong"


def test_rejected_proposal_fixed_after_feedback():
    missing = {**SAME_AS_RULES, "steps": SAME_AS_RULES["steps"][:2]}  # forgets the guarantee
    plan, rep = make_plan(bakery(), POLICY, [], 1, brain=Scripted(missing, SAME_AS_RULES), planner="agent")
    assert rep.source == "agent" and rep.attempts == 2 and not rep.agent_issues


def test_forbidden_and_unknown_remedies_never_run():
    sneaky = {**SAME_AS_RULES, "steps": SAME_AS_RULES["steps"] + [{"remedy": "HIDE_DEBT", "fixes": []}]}
    _, rep = make_plan(bakery(), POLICY, [], 1, brain=Scripted(sneaky, sneaky), planner="agent")
    assert rep.source == "rules"


def test_owner_declines_guarantee_agent_finds_another_lender():
    """The rule planner stops when the owner says no to Kafalah; the agent switches to the
    lender that does not ask for security, and the journey still ends ready."""
    s = bakery()
    no_kafalah = lambda st: st.remedy != "ADD_KAFALAH"  # noqa: E731
    assert run_journey(s, POLICY, approve=no_kafalah).outcome == "owner_declined"

    brain = Scripted(SAME_AS_RULES, {"lender": "digital_lender_invoice", "reasoning": "no security needed there",
                                     "steps": [{"remedy": "CHASE_RECEIVABLES", "fixes": ["RECEIVABLES_OVERDUE"]}]})
    t = run_journey(s, POLICY, approve=no_kafalah,
                    plan_fn=lambda *a: make_plan(*a[:4], brain=brain, month=a[4], planner="agent"))
    assert t.outcome == "ready" and t.final_policy == "digital_lender_invoice"
    assert brain.seen[1]["declined"] == ["ADD_KAFALAH"]
    assert any(r.source == "agent" for r in t.planning)


def test_rules_mode_and_no_model_never_call_the_brain():
    brain = Scripted(SAME_AS_RULES)
    _, rep = make_plan(bakery(), POLICY, [], 1, brain=brain, planner="rules")
    assert rep.source == "rules" and not brain.seen
    _, rep = make_plan(bakery(), POLICY, [], 1, brain=Scripted(), planner="agent")
    assert rep.source == "rules" and "unavailable" in rep.why


def test_journey_graph_uses_and_logs_the_agent_plan(tmp_path):
    """Through the real journey graph: the owner says no to Kafalah, the agent re-plans to the
    digital lender, the bank approves, and every choice is in the audit log."""
    from langgraph.checkpoint.memory import MemorySaver

    from app.agent.brain import TemplateBrain
    from app.agent.service import JourneyService

    class Brain(TemplateBrain):
        def __init__(self):
            super().__init__()
            self.script = Scripted(SAME_AS_RULES, {"lender": "digital_lender_invoice", "reasoning": "no security there",
                                                   "steps": [{"remedy": "CHASE_RECEIVABLES",
                                                              "fixes": ["RECEIVABLES_OVERDUE"]}]})

        def propose_plan(self, brief, feedback):
            return self.script.propose_plan(brief, feedback)

    svc = JourneyService(checkpointer=MemorySaver(), brain=Brain(), sessions_dir=tmp_path)
    jid = svc.start("demo-bakery-supplier", level="clean").journey_id
    svc.act(jid, {"type": "consent", "given": True})
    for _ in range(20):
        w = svc.waiting_for(jid)
        if w is None:
            break
        if w["await"] == "owner":
            j = svc.get(jid)
            pending = w["pending"]
            no = [i for i in pending if j.step(i).remedy == "ADD_KAFALAH"]
            yes = [i for i in pending if i not in no]
            if no:
                svc.act(jid, {"type": "decline", "step_ids": no})
            elif yes:
                svc.act(jid, {"type": "approve", "step_ids": yes})
            else:
                svc.act(jid, {"type": "advance_month"})
        elif w["await"] == "submit":
            svc.act(jid, {"type": "submit", "approve": True})
        elif w["await"] == "documents":
            svc.act(jid, {"type": "upload", "documents": w["missing"]})
    j = svc.get(jid)
    assert j.stage == "approved" and j.policy_id == "digital_lender_invoice"
    chosen = [e for e in j.events if e.kind == "plan.chosen"]
    assert len(chosen) >= 2 and all(e.data["source"] == "agent" for e in chosen)
    assert j.planning and j.planning[-1]["agent"]["ready"]
