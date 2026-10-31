"""The journey as a LangGraph state graph: from consent to the lender's yes.

    consent ─▶ extract ─▶ diagnose ─▶ plan ─▶ await_owner ─┐
                  ▲  │        ▲  │                         │ approve / decline / advance month
       await_documents  │     │  └─▶ prepare ─▶ submit_gate ─▶ submit ─▶ (approved)
                        │     └──────────────────────────────────────────┘ declined: analyse, re-plan
                        └─ (missing document)

Pauses (`interrupt`) are where a person acts: consent, uploading a missing document,
approving prepared steps, letting a month pass, and the final go before anything is
sent to a lender. At every pause the owner can also chat or assign a step to a colleague.

State is checkpointed after every node (SQLite in production), so a journey survives a
server restart and spans simulated months. The language model never routes the graph:
routing depends only on the engine's assessment and the owner's actions.

The lender's decision is the engine applied to the business's TRUE data, while the agent
works from what it extracted. If extraction got something wrong, the lender can decline
where the agent expected a yes; the agent then analyses the reasons and plans again.

Graph state: {"j": JourneyState as JSON, "truth": the true snapshot as JSON}. The truth is
kept out of JourneyState so the API can never send it to the browser.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..engine import Assessment, FinancialSnapshot, assess, load_policy
from ..extract.assemble import extract
from ..extract.llm import Reader
from .brain import GUARDRAIL_KIND, MANIPULATION, Brain, detect_lang
from .models import AssessmentView, Assignee, BlockerView, ChatMessage, JourneyState, Text
from .agent_planner import describe, make_plan
from .planner import validate_plan
from .remedies import CATALOG
from .simulator import advance_month, start_step

MAX_MONTHS = 12
MAX_SUBMISSIONS = 2


class GState(TypedDict):
    j: dict[str, Any]
    truth: dict[str, Any]


@dataclass
class Context:
    """Everything a node needs besides the state; injected when the graph is built."""

    brain: Brain
    reader_for: Callable[[str, str], Reader]       # (business_id, level) -> document reader
    docs_folder: Callable[[str], Path]             # journey_id -> its working copy of the documents
    source_folder: Callable[[str, str], Path]      # (business_id, level) -> original documents
    auto_fetch: bool = True                        # pull missing documents from their source
    planner: str | None = None                     # agent | rules (default: NEXTYES_PLANNER, else agent)


# Where the agent can pull each document itself, with the owner's consent. SIMULATED here
# (the clean copy stands in for the source's reply); in production each is an API connection:
# credit bureau (e.g. SIMAH), commercial registry (e.g. Wathq), ZATCA portal, accounting system.
SOURCES: dict[str, Text] = {
    "credit_report": Text(en="credit bureau", ar="مكتب المعلومات الائتمانية"),
    "cr_certificate": Text(en="commercial registry", ar="السجل التجاري"),
    "tax_compliance": Text(en="tax authority portal", ar="بوابة الجهة الضريبية"),
    "receivables_aging": Text(en="the business's accounting system", ar="النظام المحاسبي للمنشأة"),
    "bank_statement": Text(en="the bank (open banking)", ar="البنك (المصرفية المفتوحة)"),
}


def _load(state: GState) -> tuple[JourneyState, FinancialSnapshot | None]:
    j = JourneyState.model_validate(state["j"])
    t = FinancialSnapshot.model_validate(state["truth"]) if state.get("truth") else None
    return j, t


def _save(j: JourneyState, truth: FinancialSnapshot | None, ctx: Context) -> dict[str, Any]:
    return {"j": j.model_dump(mode="json"), "truth": truth.model_dump(mode="json") if truth else None}


def _snap(j: JourneyState) -> FinancialSnapshot:
    return FinancialSnapshot.model_validate(j.snapshot)


def view(a: Assessment, month: int) -> AssessmentView:
    p = load_policy(a.policy_id)
    return AssessmentView(
        policy_id=a.policy_id, policy_name=Text(en=p.name, ar=p.name_ar or p.name), month=month,
        score=a.score, threshold=a.ready_threshold, ready=a.ready, metrics=a.metrics,
        blockers=[BlockerView(code=b.code, severity=b.severity, message=b.message, evidence=b.evidence,
                              source=b.source, assumption=b.assumption) for b in a.blockers])


def _think(j: JourneyState, ctx: Context, method: str, *args: Any) -> Any:
    """Call the brain and charge its token use to THIS journey (the brain is shared)."""
    return _charged(j, ctx, method, lambda: getattr(ctx.brain, method)(*args))


def _charged(j: JourneyState, ctx: Context, method: str, fn: Callable[[], Any]) -> Any:
    usage = getattr(ctx.brain, "usage", None)
    before = dict(usage) if usage else {}
    if hasattr(ctx.brain, "last_error"):
        ctx.brain.last_error = None
    out = fn()
    for k, v in (usage or {}).items():
        j.usage[f"brain_{k}"] = j.usage.get(f"brain_{k}", 0) + v - before.get(k, 0)
    err = getattr(ctx.brain, "last_error", None)
    if err:  # never silent: the audit log shows a template answered instead of the model
        j.log("system", "brain.fallback", f"The language model was unavailable for {method}; a template answer was used.",
              f"تعذّر الوصول إلى النموذج اللغوي ({method})؛ استُخدم نص جاهز.", error=err)
    return out


# ---------------------------------------------------------------- side actions (any pause)


def side_action(j: JourneyState, action: dict[str, Any], ctx: Context) -> bool:
    """Chat and assignment can happen at any pause; they never move the journey."""
    kind = action.get("type")
    if kind == "chat":
        text = str(action.get("text", ""))[:2000]
        lang = detect_lang(text)
        j.messages.append(ChatMessage(role="owner", text=text, lang=lang))
        category = _think(j, ctx, "screen", text)
        if category:
            alt = MANIPULATION.get(category, MANIPULATION["other"])
            j.messages.append(ChatMessage(role="agent", text=alt.ar if lang == "ar" else alt.en, lang=lang, refused=True))
            kind = GUARDRAIL_KIND.get(category, "guardrail.refused")
            if kind == "guardrail.refused":
                en, ar = (f"Refused a request to mislead the lender ({category}); offered a lawful alternative.",
                          f"رُفض طلب لتضليل الممول ({category})؛ وقُدّم بديل نظامي.")
            elif kind == "guardrail.injection":
                en, ar = ("Ignored an attempt to override the agent's instructions.", "تُجوهلت محاولة لتجاوز تعليمات الوكيل.")
            else:
                en, ar = ("Declined an off-topic request.", "اعتُذر عن طلب خارج نطاق الخدمة.")
            j.log("agent", kind, en, ar, category=category)
        else:
            j.messages.append(ChatMessage(role="agent", text=_think(j, ctx, "reply", j, text, lang), lang=lang))
        return True
    if kind == "assign":
        st = j.step(action["step_id"])
        st.assignee = Assignee(name=action["name"], department=action.get("department", ""))
        j.log("owner", "step.assigned", f"{st.title.en} assigned to {st.assignee.name}.",
              f"أُسندت خطوة «{st.title.ar}» إلى {st.assignee.name}.", step_id=st.step_id)
        return True
    return False


# ---------------------------------------------------------------- nodes


def make_nodes(ctx: Context) -> dict[str, Callable[[GState], Command]]:

    def consent(state: GState) -> Command:
        action = interrupt({"await": "consent", "sources": [s.model_dump() for s in SOURCES.values()]})
        j, t = _load(state)
        if side_action(j, action, ctx):
            return Command(update=_save(j, t, ctx), goto="consent")
        j.consent = bool(action.get("given"))
        if not j.consent:
            j.stage = "no_consent"
            j.log("owner", "consent.refused", "The owner did not consent; nothing was read.", "لم يوافق المالك؛ لم تُقرأ أي بيانات.")
            return Command(update=_save(j, t, ctx), goto=END)
        j.log("owner", "consent.given",
              "The owner consented to reading the business's documents and to the agent fetching missing ones "
              "from their sources (" + ", ".join(s.en for s in SOURCES.values()) + ").",
              "وافق المالك على قراءة مستندات المنشأة وعلى أن يجلب الوكيل الناقص منها من مصادره ("
              + "، ".join(s.ar for s in SOURCES.values()) + ").")
        return Command(update=_save(j, t, ctx), goto="extract")

    def extract_node(state: GState) -> Command:
        j, t = _load(state)
        folder = ctx.docs_folder(j.journey_id)
        result = extract(folder, ctx.reader_for(j.business_id, j.level), j.business_id)
        j.missing_documents = result.missing_documents
        j.conflicts = [c.model_dump() for c in result.conflicts]
        j.extraction_checks = [c.model_dump() for c in result.checks]
        j.extraction_notes = result.notes
        for k, v in result.usage.items():
            j.usage[f"extract_{k}"] = j.usage.get(f"extract_{k}", 0) + v
        j.log("agent", "extract.done", f"Read {len(list(folder.glob('*.pdf')))} documents.",
              f"قُرئت {len(list(folder.glob('*.pdf')))} مستندات.", usage=result.usage,
              checks={c.name: c.passed for c in result.checks})
        for c in result.conflicts:
            j.log("agent", "extract.conflict", c.message, f"تعارض بين المستندات: {c.code}", code=c.code)
        for e in result.embedded_instructions:
            j.log("agent", "guardrail.document_instruction",
                  f"Ignored an instruction aimed at the AI reader in {e.document}; flagged for the analyst.",
                  f"تجاهلنا تعليمات موجّهة للقارئ الآلي في {e.document}؛ ونُبّه المحلل.",
                  document=e.document, text=e.text, found_by=e.found_by)
        j.extraction_injections = [e.model_dump() for e in result.embedded_instructions]
        if result.missing_documents:
            fetchable = [d for d in result.missing_documents if ctx.auto_fetch and d in SOURCES
                         and d not in j.fetched_documents
                         and (ctx.source_folder(j.business_id, "clean") / f"{d}.pdf").exists()]
            if fetchable:  # the agent gets them itself: no one has to upload anything
                return Command(update=_save(j, t, ctx), goto="fetch_documents")
            j.stage = "awaiting_documents"
            j.log("agent", "documents.requested", "Requested from the owner: " + ", ".join(result.missing_documents),
                  "طُلب من المالك: " + "، ".join(result.missing_documents), documents=result.missing_documents)
            return Command(update=_save(j, t, ctx), goto="await_documents")
        if result.snapshot is None:
            j.stage = "escalated"
            j.log("agent", "extract.failed", "Some documents could not be read; handed to an advisor.",
                  "تعذّرت قراءة بعض المستندات؛ أُحيل الملف إلى مستشار.", unreadable=result.unreadable_documents,
                  unresolved=result.unresolved_fields)
            return Command(update=_save(j, t, ctx), goto=END)
        j.snapshot = result.snapshot.model_dump(mode="json")
        return Command(update=_save(j, t, ctx), goto="diagnose")

    def fetch_documents(state: GState) -> Command:
        j, t = _load(state)
        src, dst = ctx.source_folder(j.business_id, "clean"), ctx.docs_folder(j.journey_id)
        for name in j.missing_documents:
            if name in SOURCES and name not in j.fetched_documents and (src / f"{name}.pdf").exists():
                shutil.copy(src / f"{name}.pdf", dst / f"{name}.pdf")
                j.fetched_documents.append(name)
                where = SOURCES[name]
                j.log("agent", "documents.fetched", f"Fetched the missing {name.replace('_', ' ')} from {where.en} (simulated connection).",
                      f"جلب الوكيل المستند الناقص ({name}) من {where.ar} (ربط محاكى).", document=name, source=where.en)
        return Command(update=_save(j, t, ctx), goto="extract")

    def await_documents(state: GState) -> Command:
        action = interrupt({"await": "documents", "missing": state["j"]["missing_documents"]})
        j, t = _load(state)
        if side_action(j, action, ctx):
            return Command(update=_save(j, t, ctx), goto="await_documents")
        src, dst = ctx.source_folder(j.business_id, "clean"), ctx.docs_folder(j.journey_id)
        for name in action.get("documents", []):
            if name in j.missing_documents and (src / f"{name}.pdf").exists():
                shutil.copy(src / f"{name}.pdf", dst / f"{name}.pdf")
                j.log("owner", "documents.uploaded", f"Uploaded {name}.", f"رُفع المستند {name}.", document=name)
        return Command(update=_save(j, t, ctx), goto="extract")

    def diagnose(state: GState) -> Command:
        j, t = _load(state)
        a = assess(_snap(j), load_policy(j.policy_id))
        j.assessment = view(a, j.month)
        j.history.append(j.assessment)
        j.log("agent", "assess", f"Score {a.score:.0f} / {a.ready_threshold:.0f} for {j.assessment.policy_name.en}: "
              + ("ready." if a.ready else f"{len(a.blockers)} issue(s)."),
              f"الدرجة {a.score:.0f} من {a.ready_threshold:.0f} لدى {j.assessment.policy_name.ar}: "
              + ("جاهزة." if a.ready else f"عدد الملاحظات {len(a.blockers)}."),
              score=a.score, ready=a.ready, blockers=a.blocker_codes)
        if a.ready:
            return Command(update=_save(j, t, ctx), goto="prepare")
        if j.month >= MAX_MONTHS:
            j.stage = "out_of_time"
            return Command(update=_save(j, t, ctx), goto=END)
        return Command(update=_save(j, t, ctx), goto="plan")

    def plan(state: GState) -> Command:
        j, t = _load(state)
        s = _snap(j)
        p, report = _charged(j, ctx, "propose_plan", lambda: make_plan(
            s, j.policy_id, j.steps, first_id=len(j.steps) + 1, brain=ctx.brain, month=j.month, planner=ctx.planner))
        if report.rules is not None:  # two plans were compared: say whose plan runs and why
            line = describe(report)
            j.log("agent", "plan.chosen", line.en, line.ar, **report.model_dump(mode="json"))
            j.planning.append({"month": j.month, **report.model_dump(mode="json")})
        issues = validate_plan(p, s, j.steps)
        if issues:  # never act on an invalid plan
            j.stage = "escalated"
            j.log("system", "plan.invalid", "The plan failed validation; handed to an advisor.",
                  "لم تجتز الخطة التحقق؛ أُحيل الملف إلى مستشار.", issues=[i.model_dump() for i in issues])
            return Command(update=_save(j, t, ctx), goto=END)
        for st in p.steps:
            j.steps.append(st)
            if st.executor == "approve":
                st.status = "awaiting_approval"
            elif st.executor == "advisor":
                st.status = "in_progress"
            else:
                s, t = _start(st, s, t, j.month)
            j.log("agent", "plan.step", f"{st.title.en}: {st.detail.en}", f"{st.title.ar}: {st.detail.ar}",
                  step_id=st.step_id, executor=st.executor, remedy=st.remedy)
        j.snapshot = s.model_dump(mode="json")
        if p.estimated_months is None:
            j.stage = "owner_declined" if p.declined else ("escalated" if p.unfixable else "not_reachable")
            j.log("agent", f"journey.{j.stage}", _END_TEXT[j.stage].en, _END_TEXT[j.stage].ar,
                  unfixable=p.unfixable, declined=p.declined)
            return Command(update=_save(j, t, ctx), goto=END)
        if p.steps:
            j.plan_summary = _think(j, ctx, "explain_plan", j)
        j.stage = "working"
        return Command(update=_save(j, t, ctx), goto="await_owner")

    def await_owner(state: GState) -> Command:
        action = interrupt({"await": "owner", "pending": [s["step_id"] for s in state["j"]["steps"]
                                                          if s["status"] == "awaiting_approval"]})
        j, t = _load(state)
        if side_action(j, action, ctx):
            return Command(update=_save(j, t, ctx), goto="await_owner")
        kind = action.get("type")
        s = _snap(j)
        if kind in ("approve", "decline"):
            for sid in action.get("step_ids", []):
                st = j.step(sid)
                if st.status != "awaiting_approval":
                    continue
                if kind == "decline":
                    st.status = "declined"
                    j.log("owner", "step.declined", f"Declined: {st.title.en}.", f"رُفضت: {st.title.ar}.", step_id=sid)
                elif st.remedy == "SWITCH_LENDER":
                    j.policy_id = st.params["policy_id"]
                    st.status, st.started_month, st.done_month = "done", j.month, j.month
                    j.log("owner", "step.approved", f"Approved: {st.detail.en}", f"وافق المالك: {st.detail.ar}", step_id=sid)
                else:
                    s, t = _start(st, s, t, j.month)
                    j.log("owner", "step.approved", f"Approved: {st.title.en}.", f"وافق المالك: {st.title.ar}.", step_id=sid)
        elif kind == "advance_month":
            before = {st.step_id: st.status for st in j.steps}
            truth_steps = [st.model_copy(deep=True) for st in j.steps]
            s = advance_month(s, j.steps, j.month, load_policy(j.policy_id))
            t = advance_month(t, truth_steps, j.month, load_policy(j.policy_id)) if t else t
            j.month += 1
            j.log("system", "month.advanced", f"One month passed (month {j.month}).", f"مضى شهر (الشهر {j.month}).")
            for st in j.steps:
                if before[st.step_id] != "done" and st.status == "done":
                    j.log("agent", "step.done", f"Done: {st.title.en}.", f"اكتملت: {st.title.ar}.", step_id=st.step_id)
        j.snapshot = s.model_dump(mode="json")
        return Command(update=_save(j, t, ctx), goto="diagnose")

    def prepare(state: GState) -> Command:
        j, t = _load(state)
        folder = ctx.docs_folder(j.journey_id)
        j.application = {
            "lender": j.policy_id, "prepared_month": j.month,
            "request": _snap(j).request.model_dump(mode="json"),
            "score": j.assessment.score, "threshold": j.assessment.threshold,
            "snapshot": j.snapshot,
            "documents": sorted(p.stem for p in folder.glob("*.pdf")),
            "steps_completed": [{"step_id": s.step_id, "action": s.title.en, "detail": s.detail.en}
                                for s in j.steps if s.status == "done"],
            "conflicts_resolved": j.conflicts,
            "embedded_instructions": j.extraction_injections,
            "extraction_checks": j.extraction_checks,
        }
        j.stage = "awaiting_submit"
        j.log("agent", "application.compiled", "Application compiled; waiting for the owner's approval to submit.",
              "جُهّز الطلب؛ بانتظار موافقة المالك على التقديم.")
        return Command(update=_save(j, t, ctx), goto="submit_gate")

    def submit_gate(state: GState) -> Command:
        action = interrupt({"await": "submit"})
        j, t = _load(state)
        if side_action(j, action, ctx):
            return Command(update=_save(j, t, ctx), goto="submit_gate")
        if not action.get("approve"):
            j.stage = "working"
            j.log("owner", "submit.held", "The owner chose not to submit yet.", "اختار المالك عدم التقديم الآن.")
            return Command(update=_save(j, t, ctx), goto="await_owner")
        j.log("owner", "submit.approved", "The owner approved submitting the application.", "وافق المالك على تقديم الطلب.")
        return Command(update=_save(j, t, ctx), goto="submit")

    def submit(state: GState) -> Command:
        j, t = _load(state)
        j.stage = "submitted"
        decision = assess(t, load_policy(j.policy_id))  # the lender sees the true business
        record = {"month": j.month, "lender": j.policy_id, "approved": decision.ready, "score": decision.score,
                  "reasons": [b.message for b in decision.blockers if not decision.ready]}
        j.submissions.append(record)
        if decision.ready:
            j.stage = "approved"
            j.log("lender", "lender.approved", f"Approved by {j.assessment.policy_name.en}.",
                  f"وافق {j.assessment.policy_name.ar} على الطلب.", **record)
            return Command(update=_save(j, t, ctx), goto=END)
        j.log("lender", "lender.declined", "Declined: " + "; ".join(record["reasons"]),
              "رُفض الطلب: " + "؛ ".join(record["reasons"]), **record)
        analysis = _think(j, ctx, "analyse_decline", j, record["reasons"])
        j.log("agent", "decline.analysed", analysis.en, analysis.ar)
        j.snapshot = t.model_dump(mode="json")  # the lender's figures replace what we had extracted
        if len(j.submissions) >= MAX_SUBMISSIONS:
            j.stage = "escalated"
            return Command(update=_save(j, t, ctx), goto=END)
        return Command(update=_save(j, t, ctx), goto="diagnose")

    return {"consent": consent, "extract": extract_node, "fetch_documents": fetch_documents,
            "await_documents": await_documents,
            "diagnose": diagnose, "plan": plan, "await_owner": await_owner, "prepare": prepare,
            "submit_gate": submit_gate, "submit": submit}


def _start(st, s: FinancialSnapshot, t: FinancialSnapshot | None, month: int):
    """Start a step on the agent's view and, with a copy of the step, on the true data."""
    twin = st.model_copy(deep=True)
    s = start_step(s, st, month)
    if t is not None:
        t = start_step(t, twin, month)
    return s, t


_END_TEXT = {
    "owner_declined": Text(en="A required step was declined, so the journey stopped. It can restart at any time.",
                           ar="رُفضت خطوة لازمة، فتوقفت الرحلة. يمكن استئنافها في أي وقت."),
    "escalated": Text(en="No remedy within reach; a human advisor takes over.", ar="لا يوجد حل متاح؛ يتولى مستشار بشري الملف."),
    "not_reachable": Text(en="No lender can say yes within 12 months; we will tell you when to come back.",
                          ar="لا يمكن لأي ممول القبول خلال 12 شهرًا؛ سنخبرك متى تعود."),
}

_DESTINATIONS = {
    "consent": ("consent", "extract", END), "extract": ("fetch_documents", "await_documents", "diagnose", END),
    "fetch_documents": ("extract",),
    "await_documents": ("await_documents", "extract"), "diagnose": ("prepare", "plan", END),
    "plan": ("await_owner", END), "await_owner": ("await_owner", "diagnose"), "prepare": ("submit_gate",),
    "submit_gate": ("submit_gate", "submit", "await_owner"), "submit": ("diagnose", END),
}


def build_graph(ctx: Context, checkpointer=None):
    g = StateGraph(GState)
    for name, fn in make_nodes(ctx).items():
        g.add_node(name, fn, destinations=_DESTINATIONS[name])
    g.add_edge(START, "consent")
    return g.compile(checkpointer=checkpointer)


def new_journey(journey_id: str, business_id: str, name: Text, sector: Text, level: str, policy_id: str) -> JourneyState:
    j = JourneyState(journey_id=journey_id, business_id=business_id, business_name=name, sector=sector,
                     level=level, start_policy=policy_id, policy_id=policy_id)
    j.log("system", "journey.started", f"Journey started for {name.en}.", f"بدأت الرحلة لـ {name.ar}.",
          level=level, lender=policy_id)
    return j


__all__ = ["build_graph", "Context", "GState", "new_journey", "view", "CATALOG"]
