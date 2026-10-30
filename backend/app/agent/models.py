"""The agent's state, as plain data.

Everything here is a pydantic model, so the API can return it as JSON unchanged and
the web app can render it without extra mapping. Every user-facing text has an
English and an Arabic version.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Who carries out a plan step. This split is how we show "minimal human intervention":
#   agent    the agent does it on its own (e.g. sends payment reminders)
#   approve  the agent prepares it, the owner approves with one click (e.g. resize the request)
#   owner    only the owner can do it; the agent follows up (e.g. settle a default)
#   wait     nothing to do but let time pass (e.g. operating history); the agent re-checks monthly
#   advisor  needs a human advisor (escalation)
Executor = Literal["agent", "approve", "owner", "wait", "advisor"]
StepStatus = Literal["proposed", "awaiting_approval", "in_progress", "done", "declined"]


class Text(BaseModel):
    en: str
    ar: str


class PlanStep(BaseModel):
    step_id: str                      # unique within a journey, e.g. "s3"
    remedy: str                       # catalog id, e.g. RESIZE_REQUEST
    fixes: list[str]                  # blocker codes this step addresses
    executor: Executor
    title: Text
    detail: Text                      # concrete: amounts, dates, what exactly happens
    params: dict[str, Any] = Field(default_factory=dict)
    duration_months: int = 0          # months after starting until the effect shows in the data
    status: StepStatus = "proposed"
    started_month: int | None = None  # journey month when work started
    done_month: int | None = None
    assignee: "Assignee | None" = None  # owner steps: the person / department handling it


class Plan(BaseModel):
    policy_id: str                    # the lender this plan targets
    steps: list[PlanStep]
    estimated_months: int | None      # None: cannot reach ready with known remedies
    unfixable: list[str] = Field(default_factory=list)  # blockers no remedy covers -> advisor
    declined: list[str] = Field(default_factory=list)   # blockers whose remedy the owner declined


class PlanIssue(BaseModel):
    """A problem the plan validator found. Any issue means the plan is rejected."""

    code: str
    message: str


# ---------------------------------------------------------------- the journey (Chunk 4b)

Stage = Literal[
    "consent",             # waiting for the owner's consent to read their data
    "awaiting_documents",  # a required document is missing; the owner is asked to upload it
    "working",             # plan running; waiting for approvals or for time to pass
    "awaiting_submit",     # ready; the application is compiled and waits for the owner's go
    "submitted",
    # terminal
    "approved", "no_consent", "escalated", "not_reachable", "owner_declined", "out_of_time",
]
Actor = Literal["agent", "owner", "lender", "system"]


class Assignee(BaseModel):
    """Who inside the business handles an owner step (set from the company panel)."""

    name: str
    department: str = ""


class Event(BaseModel):
    """One line of the audit log, also the UI timeline. Every tool call is recorded."""

    seq: int
    month: int
    actor: Actor
    kind: str                         # e.g. extract.done, plan.created, step.approved, guardrail.refused
    text: Text
    data: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["owner", "agent"]
    text: str
    lang: Literal["en", "ar"] = "en"
    refused: bool = False             # a guardrail refusal


class BlockerView(BaseModel):
    code: str
    severity: str
    message: str
    evidence: dict[str, Any]
    source: str
    assumption: bool


class AssessmentView(BaseModel):
    policy_id: str
    policy_name: Text
    month: int
    score: float
    threshold: float
    ready: bool
    blockers: list[BlockerView]
    metrics: dict[str, Any]


class JourneyState(BaseModel):
    journey_id: str
    business_id: str
    business_name: Text
    sector: Text
    level: str                        # document difficulty used for this journey
    start_policy: str
    policy_id: str                    # current target lender
    month: int = 0
    stage: Stage = "consent"
    consent: bool | None = None

    missing_documents: list[str] = Field(default_factory=list)
    fetched_documents: list[str] = Field(default_factory=list)  # pulled by the agent from their source
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    extraction_checks: list[dict[str, Any]] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)
    extraction_injections: list[dict[str, Any]] = Field(default_factory=list)  # instructions found in documents

    snapshot: Any = None              # FinancialSnapshot (as dict) the agent works from
    truth: Any = Field(default=None, exclude=True)  # simulation's true data: never sent to the UI
    assessment: AssessmentView | None = None
    history: list[AssessmentView] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    plan_summary: Text | None = None
    application: dict[str, Any] | None = None
    submissions: list[dict[str, Any]] = Field(default_factory=list)  # lender decisions

    events: list[Event] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    usage: dict[str, float] = Field(default_factory=dict)

    def log(self, actor: Actor, kind: str, en: str, ar: str, **data: Any) -> None:
        self.events.append(Event(seq=len(self.events) + 1, month=self.month, actor=actor, kind=kind,
                                 text=Text(en=en, ar=ar), data=data))

    def step(self, step_id: str) -> PlanStep:
        return next(s for s in self.steps if s.step_id == step_id)

    def pending(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "awaiting_approval"]


PlanStep.model_rebuild()
