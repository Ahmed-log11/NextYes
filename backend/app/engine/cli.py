"""Score a snapshot from the command line.

    python -m app.engine.cli examples/bakery_supplier.json
    python -m app.engine.cli examples/bakery_supplier.json --policy digital_lender_invoice
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import assess
from .models import FinancialSnapshot
from .policy import available_policies, load_policy


def main() -> None:
    ap = argparse.ArgumentParser(description="Assess funding readiness for one business.")
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--policy", default="commercial_bank_sme", choices=available_policies())
    ap.add_argument("--json", action="store_true", help="print the full assessment as JSON")
    args = ap.parse_args()

    snap = FinancialSnapshot.model_validate_json(args.snapshot.read_text())
    policy = load_policy(args.policy)
    result = assess(snap, policy)

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return

    verdict = "READY" if result.ready else "NOT READY"
    print(f"{policy.name}  (policy v{result.policy_version})")
    print(f"{snap.business_id}: score {result.score} / 100, threshold {result.ready_threshold} → {verdict}")
    print(f"metrics: {result.metrics}")
    if result.blockers:
        print("\nWhy a lender would decline today:")
        for b in result.blockers:
            tag = " [assumed threshold]" if b.assumption else ""
            print(f"  {b.code:<20} {b.severity:<4}  {b.message}{tag}")


if __name__ == "__main__":
    main()
