"""The one entry point the API calls: start a journey, act on it, read it.

    svc = JourneyService()                      # SQLite checkpoints in backend/sessions/
    j = svc.start("demo-bakery-supplier", level="realistic")
    j = svc.act(j.journey_id, {"type": "consent", "given": True})
    svc.waiting_for(j.journey_id)               # {"await": "owner", "pending": ["s1", "s2"]}
    j = svc.act(j.journey_id, {"type": "approve", "step_ids": ["s1", "s2"]})
    j = svc.act(j.journey_id, {"type": "advance_month"})

Actions (each is checked against what the journey is waiting for; a wrong one raises
`ActionError`, which the API turns into a 400):
    consent         {"given": bool}                        at consent
    upload          {"documents": [names]}                 at documents
    approve/decline {"step_ids": [...]}                    at owner
    advance_month   {}                                     at owner
    submit          {"approve": bool}                      at submit
    chat            {"text": str}                          at any pause
    assign          {"step_id", "name", "department"}      at any pause

Each journey gets its own copy of the documents (backend/sessions/<id>/documents), so an
upload in one journey never changes the dataset or another journey.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command

from ..extract.llm import Reader
from ..synth.dataset import DATA_DIR
from ..synth.generator import SyntheticBusiness
from .brain import Brain, default_brain
from .graph import Context, build_graph, new_journey
from .models import JourneyState, Text

SESSIONS_DIR = Path(__file__).resolve().parents[2] / "sessions"
SPLITS = ("demo", "dev", "heldout")

ALLOWED = {
    "consent": {"consent"},
    "documents": {"upload"},
    "owner": {"approve", "decline", "advance_month"},
    "submit": {"submit"},
}
ANYWHERE = {"chat", "assign"}


class ActionError(ValueError):
    pass


def find_business(business_id: str, data_dir: Path = DATA_DIR) -> tuple[str, SyntheticBusiness, Path]:
    for split in SPLITS:
        folder = data_dir / split / business_id
        if (folder / "business.json").exists():
            b = SyntheticBusiness.model_validate(json.loads((folder / "business.json").read_text(encoding="utf-8")))
            return split, b, folder
    raise ActionError(f"unknown business {business_id}")


def default_reader(kind: str = "oracle"):
    """`oracle` reads the true values (no API key); `haiku` reads the PDFs with the model."""
    def make(business_id: str, level: str) -> Reader:
        if kind == "haiku":
            from ..extract.llm import AnthropicReader, CachedReader
            return CachedReader(AnthropicReader())
        from ..extract.oracle import OracleReader
        return OracleReader(find_business(business_id)[1], level)  # type: ignore[arg-type]
    return make


class JourneyService:
    def __init__(self, checkpointer=None, brain: Brain | None = None, reader: str | Any = "oracle",
                 sessions_dir: Path = SESSIONS_DIR, data_dir: Path = DATA_DIR, auto_fetch: bool = True):
        self.sessions_dir, self.data_dir = sessions_dir, data_dir
        if checkpointer is None:
            from langgraph.checkpoint.sqlite import SqliteSaver
            sessions_dir.mkdir(parents=True, exist_ok=True)
            checkpointer = SqliteSaver(sqlite3.connect(sessions_dir / "journeys.sqlite", check_same_thread=False))
        self.brain = brain or default_brain()
        ctx = Context(
            brain=self.brain,
            reader_for=default_reader(reader) if isinstance(reader, str) else reader,  # or a (business, level) -> Reader
            docs_folder=lambda jid: self.sessions_dir / jid / "documents",
            source_folder=lambda bid, level: find_business(bid, self.data_dir)[2] / "documents" / level,
            auto_fetch=auto_fetch,
        )
        self.graph = build_graph(ctx, checkpointer)

    @staticmethod
    def _cfg(journey_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": journey_id}}

    def start(self, business_id: str, level: str = "realistic", policy_id: str = "commercial_bank_sme") -> JourneyState:
        split, b, folder = find_business(business_id, self.data_dir)
        src = folder / "documents" / level
        if not (src / "noise.json").exists():
            raise ActionError(f"no {level} documents for {business_id}; run python -m app.synth.documents --split {split}")
        journey_id = uuid.uuid4().hex[:12]
        dst = self.sessions_dir / journey_id / "documents"
        dst.mkdir(parents=True)
        for f in src.glob("*.pdf"):
            shutil.copy(f, dst / f.name)
        m = b.meta
        j = new_journey(journey_id, business_id, Text(en=m.name_en, ar=m.name_ar), Text(en=m.sector_en, ar=m.sector_ar),
                        level, policy_id)
        self.graph.invoke({"j": j.model_dump(mode="json"), "truth": b.snapshot.model_dump(mode="json")},
                          self._cfg(journey_id))
        return self.get(journey_id)

    def get(self, journey_id: str) -> JourneyState:
        snap = self.graph.get_state(self._cfg(journey_id))
        if not snap.values:
            raise ActionError(f"unknown journey {journey_id}")
        return JourneyState.model_validate(snap.values["j"])

    def waiting_for(self, journey_id: str) -> dict[str, Any] | None:
        snap = self.graph.get_state(self._cfg(journey_id))
        for task in snap.tasks:
            for intr in task.interrupts:
                return dict(intr.value)
        return None

    def act(self, journey_id: str, action: dict[str, Any]) -> JourneyState:
        waiting = self.waiting_for(journey_id)
        if waiting is None:
            raise ActionError("this journey has ended")
        kind = action.get("type")
        if kind not in ALLOWED[waiting["await"]] | ANYWHERE:
            raise ActionError(f"'{kind}' is not possible now; the journey is waiting for: {waiting['await']}")
        j = self.get(journey_id)
        ids = {s.step_id for s in j.steps}
        if kind in ("approve", "decline"):
            bad = [i for i in action.get("step_ids", []) if i not in waiting.get("pending", [])]
            if bad or not action.get("step_ids"):
                raise ActionError(f"not awaiting approval: {bad or 'no steps given'}")
        if kind == "assign" and (action.get("step_id") not in ids or not action.get("name")):
            raise ActionError("assign needs an existing step_id and a name")
        if kind == "upload" and not action.get("documents"):
            raise ActionError("upload needs the document names")
        if kind == "chat" and not str(action.get("text", "")).strip():
            raise ActionError("empty message")
        self.graph.invoke(Command(resume=action), self._cfg(journey_id))
        return self.get(journey_id)

    def mermaid(self) -> str:
        """The graph as a Mermaid diagram (for the slides)."""
        return self.graph.get_graph().draw_mermaid()
