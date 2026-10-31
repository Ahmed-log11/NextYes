"""NextYes HTTP API: a thin layer over JourneyService for the web app.

    uvicorn app.api.main:app --reload                 # local, http://127.0.0.1:8000/docs
    uvicorn app.api.main:app --host 0.0.0.0 --port $PORT   # Render

Configuration (environment or backend/.env):
    ANTHROPIC_API_KEY     enables the Haiku reader and the Sonnet brain (server side only)
    NEXTYES_READER        haiku | oracle (default: haiku if a key is set, else oracle)
    NEXTYES_CORS          comma-separated allowed origins (default: local dev servers + *.vercel.app)
    NEXTYES_SESSIONS_DIR  where journeys and their documents live (default backend/sessions)

Every response about a journey has the same shape, {"journey": ..., "waiting": ...}: the
full journey state (JourneyState, never the simulation's true data) and what it is waiting
for, so the web app always knows which buttons to show.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..engine import available_policies, load_policy
from ..extract.llm import _load_dotenv
from ..synth.dataset import DATA_DIR
from ..agent.service import SESSIONS_DIR, ActionError, JourneyService, find_business

_load_dotenv()
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = BACKEND_DIR / "reports"
LEVELS = ("clean", "realistic", "hard")
DEMO_SPLIT = "demo"


# ---------------------------------------------------------------- rate limiting


class RateLimiter:
    """Sliding-window limits per client, in memory (one server instance is enough for the demo).
    Protects the API credit: judges can click freely, a script cannot drain it."""

    LIMITS = {"start": (10, 3600), "chat": (30, 600), "action": (120, 600)}

    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client: str, kind: str) -> None:
        limit, window = self.LIMITS[kind]
        now = time.monotonic()
        with self.lock:
            q = self.hits[(client, kind)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(429, f"Too many requests ({kind}); please wait a few minutes.")
            q.append(now)


class JourneyLocks:
    """A lock per journey: two clicks on the same journey wait for each other, but a long
    document read in one journey never blocks other visitors. (The SQLite checkpointer
    serialises its own writes.)"""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def __call__(self, journey_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(journey_id, threading.Lock())


# ---------------------------------------------------------------- app


class StartJourney(BaseModel):
    business_id: str
    level: str = Field("realistic", description="document difficulty: clean | realistic | hard")
    policy_id: str = "commercial_bank_sme"


class Action(BaseModel):
    """One owner action. `type` decides which other fields matter (see agent/service.py)."""

    type: str
    given: bool | None = None          # consent
    documents: list[str] | None = None  # upload
    step_ids: list[str] | None = None   # approve / decline
    approve: bool | None = None         # submit
    text: str | None = None             # chat
    step_id: str | None = None          # assign
    name: str | None = None
    department: str | None = None


def _reader_kind() -> str:
    default = "haiku" if os.environ.get("ANTHROPIC_API_KEY") else "oracle"
    return os.environ.get("NEXTYES_READER", default)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "service"):  # tests inject their own
        sessions = Path(os.environ.get("NEXTYES_SESSIONS_DIR", SESSIONS_DIR))
        app.state.service = JourneyService(reader=_reader_kind(), sessions_dir=sessions)
    app.state.locks = JourneyLocks()       # one journey at a time per journey; journeys run in parallel
    app.state.limiter = RateLimiter()
    yield


app = FastAPI(title="NextYes API", version="0.1.0", lifespan=lifespan,
              description="From a financing 'not yet' to a 'yes': the agent's journey over HTTP.")

_origins = os.environ.get("NEXTYES_CORS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def _svc(request: Request) -> JourneyService:
    return request.app.state.service


def _payload(svc: JourneyService, journey_id: str) -> dict[str, Any]:
    return {"journey": json.loads(svc.get(journey_id).model_dump_json()), "waiting": svc.waiting_for(journey_id)}


# ---------------------------------------------------------------- read-only catalogue


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    svc = _svc(request)
    from ..agent.agent_planner import PLANNER
    return {"ok": True, "reader": _reader_kind(), "brain": getattr(svc.brain, "name", "?"), "planner": PLANNER}


@app.get("/api/businesses")
def businesses() -> list[dict[str, Any]]:
    """The demo businesses a visitor can start a journey for. What the problems are is NOT
    included: finding them is the agent's job."""
    index = json.loads((DATA_DIR / DEMO_SPLIT / "index.json").read_text(encoding="utf-8"))
    out = []
    for row in index:
        _, b, folder = find_business(row["business_id"])
        m, r = b.meta, b.snapshot.request
        out.append({
            "business_id": m.business_id, "name": {"en": m.name_en, "ar": m.name_ar},
            "sector": {"en": m.sector_en, "ar": m.sector_ar}, "city": {"en": m.city_en, "ar": m.city_ar},
            "request": {"amount_sar": r.amount_sar, "tenor_months": r.tenor_months},
            "levels": [lv for lv in LEVELS if (folder / "documents" / lv / "noise.json").exists()],
        })
    return out


@app.get("/api/policies")
def policies() -> list[dict[str, Any]]:
    """Lender policies with every rule and its public source: what the bank screen shows."""
    out = []
    for pid in available_policies():
        p = load_policy(pid)
        out.append({"policy_id": p.id, "name": {"en": p.name, "ar": p.name_ar or p.name},
                    "description": p.description, "ready_threshold": p.ready_threshold, "version": p.version,
                    "rules": [{"id": r.id, "severity": r.severity, "weight": r.weight, "params": r.params,
                               "source": r.source, "source_url": r.source_url, "assumption": r.assumption}
                              for r in p.rules]})
    return out


@app.get("/api/evaluation")
def evaluation() -> list[dict[str, Any]]:
    """Summaries of every evaluation report in backend/reports (for the results screen)."""
    out = []
    for f in sorted(REPORT_DIR.glob("extraction-*.json")):
        rep = json.loads(f.read_text(encoding="utf-8"))
        out.append({"report": f.stem, "split": rep["split"], "level": rep["level"], "reader": rep["reader"],
                    "summary": rep["summary"]})
    return out


@app.get("/api/planner-evaluation")
def planner_evaluation() -> list[dict[str, Any]]:
    """Agent planner vs rule planner (reports/planner-*.json from app.agent.evaluate_planner)."""
    out = []
    for f in sorted(REPORT_DIR.glob("planner-*.json")):
        rep = json.loads(f.read_text(encoding="utf-8"))
        out.append({"report": f.stem, "split": rep["split"], "brain": rep["brain"], "summary": rep["summary"]})
    return out


@app.get("/api/graph", response_class=PlainTextResponse)
def graph(request: Request) -> str:
    """The journey graph as Mermaid, drawn from the real LangGraph definition."""
    return _svc(request).mermaid()


# ---------------------------------------------------------------- journeys


@app.post("/api/journeys")
def start(body: StartJourney, request: Request) -> dict[str, Any]:
    request.app.state.limiter.check(_client(request), "start")
    if body.level not in LEVELS:
        raise HTTPException(400, f"level must be one of {LEVELS}")
    if body.policy_id not in available_policies():
        raise HTTPException(400, f"unknown lender policy {body.policy_id}")
    svc = _svc(request)
    try:
        j = svc.start(body.business_id, level=body.level, policy_id=body.policy_id)  # a new id: no lock needed
    except ActionError as e:
        raise HTTPException(400, str(e)) from None
    with request.app.state.locks(j.journey_id):
        return _payload(svc, j.journey_id)


@app.get("/api/journeys/{journey_id}")
def get_journey(journey_id: str, request: Request) -> dict[str, Any]:
    svc = _svc(request)
    with request.app.state.locks(journey_id):
        try:
            return _payload(svc, journey_id)
        except ActionError as e:
            raise HTTPException(404, str(e)) from None


@app.post("/api/journeys/{journey_id}/actions")
def act(journey_id: str, body: Action, request: Request) -> dict[str, Any]:
    request.app.state.limiter.check(_client(request), "chat" if body.type == "chat" else "action")
    svc = _svc(request)
    action = {k: v for k, v in body.model_dump().items() if v is not None}
    with request.app.state.locks(journey_id):
        try:
            svc.act(journey_id, action)
        except ActionError as e:
            raise HTTPException(400, str(e)) from None
        return _payload(svc, journey_id)


@app.get("/api/journeys/{journey_id}/documents")
def documents(journey_id: str, request: Request) -> list[str]:
    folder = _svc(request).sessions_dir / journey_id / "documents"
    if not folder.exists():
        raise HTTPException(404, "unknown journey")
    return sorted(p.stem for p in folder.glob("*.pdf"))


@app.get("/api/journeys/{journey_id}/documents/{name}")
def document(journey_id: str, name: str, request: Request) -> FileResponse:
    if not name.replace("_", "").isalnum():
        raise HTTPException(400, "bad document name")
    path = _svc(request).sessions_dir / journey_id / "documents" / f"{name}.pdf"
    if not path.exists():
        raise HTTPException(404, "no such document")
    return FileResponse(path, media_type="application/pdf")


@app.get("/api/journeys/{journey_id}/bank")
def bank_view(journey_id: str, request: Request) -> dict[str, Any]:
    """What the lender sees: nothing until the owner approves submission, then the compiled
    application, the decision and the full audit log."""
    svc = _svc(request)
    with request.app.state.locks(journey_id):
        try:
            j = svc.get(journey_id)
        except ActionError as e:
            raise HTTPException(404, str(e)) from None
    submitted = bool(j.submissions)
    return {
        "submitted": submitted,
        "business": {"name": j.business_name.model_dump(), "sector": j.sector.model_dump()},
        "lender": j.policy_id,
        "application": j.application if submitted else None,
        "decisions": j.submissions,
        "audit_log": [e.model_dump() for e in j.events] if submitted else [],
        "flags": {"conflicts": j.conflicts, "document_instructions": j.extraction_injections} if submitted else {},
    }
