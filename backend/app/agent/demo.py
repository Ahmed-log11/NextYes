"""Watch a whole journey in the terminal, approving everything as the owner would.

    python -m app.agent.demo demo-bakery-supplier
    python -m app.agent.demo demo-online-store --level realistic --lang ar
    python -m app.agent.demo demo-contractor --reader haiku        # real document reading
    python -m app.agent.demo --mermaid                              # write the graph diagram for slides

Uses an in-memory checkpointer and a temporary sessions folder, so it leaves nothing behind.
The brain is Sonnet when ANTHROPIC_API_KEY is set, else the template brain.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from .service import JourneyService

ICONS = {"agent": "AGENT ", "owner": "OWNER ", "lender": "LENDER", "system": "      "}


def play(svc: JourneyService, jid: str, say: str | None) -> None:
    for _ in range(40):
        w = svc.waiting_for(jid)
        if w is None:
            return
        if w["await"] == "consent":
            svc.act(jid, {"type": "consent", "given": True})
            if say:
                svc.act(jid, {"type": "chat", "text": say})
        elif w["await"] == "documents":
            svc.act(jid, {"type": "upload", "documents": w["missing"]})
        elif w["await"] == "owner":
            svc.act(jid, {"type": "approve", "step_ids": w["pending"]} if w["pending"] else {"type": "advance_month"})
        elif w["await"] == "submit":
            svc.act(jid, {"type": "submit", "approve": True})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("business_id", nargs="?")
    ap.add_argument("--level", default="clean", choices=["clean", "realistic", "hard"])
    ap.add_argument("--policy", default="commercial_bank_sme")
    ap.add_argument("--reader", default="oracle", choices=["oracle", "haiku"])
    ap.add_argument("--lang", default="en", choices=["en", "ar"])
    ap.add_argument("--say", help="a chat message to send after consent, e.g. 'Can you hide my loan?'")
    ap.add_argument("--mermaid", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    svc = JourneyService(checkpointer=MemorySaver(), reader=args.reader, sessions_dir=Path(tempfile.mkdtemp()))
    if args.mermaid:
        out = Path(__file__).resolve().parents[3] / "docs" / "journey_graph.mmd"
        out.parent.mkdir(exist_ok=True)
        out.write_text(svc.mermaid(), encoding="utf-8")
        print(f"wrote {out}")
        return
    if not args.business_id:
        ap.error("business_id is required")

    j = svc.start(args.business_id, level=args.level, policy_id=args.policy)
    play(svc, j.journey_id, args.say)
    j = svc.get(j.journey_id)
    print(f"{j.business_name.en} — {j.stage.upper()} after {j.month} month(s) · brain: {svc.brain.name}\n")
    for e in j.events:
        print(f"  m{e.month}  {ICONS[e.actor]}  {getattr(e.text, args.lang)}")
    if j.plan_summary:
        print(f"\nPlan summary: {getattr(j.plan_summary, args.lang)}")
    for m in j.messages:
        print(f"  {m.role}: {m.text}")
    done = [s for s in j.steps if s.status == "done"]
    by = {k: sum(s.executor == k for s in done) for k in ("agent", "approve", "owner", "wait")}
    print(f"\nSteps done: {len(done)} — agent alone {by['agent']}, prepared + one-click approval {by['approve']}, "
          f"owner {by['owner']}, waiting {by['wait']}")


if __name__ == "__main__":
    main()
