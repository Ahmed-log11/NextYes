"""Build the three datasets.

    python -m app.synth.dataset            # writes backend/data/{dev,heldout,demo}

- dev (40):     what we build and tune on.
- heldout (20): different seeds AND issue combinations never seen in dev.
                Not opened during development; used only for final numbers.
- demo (3):     hand-picked stories for the live demo.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .generator import SyntheticBusiness, make_business
from .issues import ALL_CODES, compatible

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

DEV_SIZE, HELDOUT_SIZE = 40, 20
DEV_CLEAN, HELDOUT_CLEAN = 4, 2  # businesses with no issues: tests false alarms
SIZE_WEIGHTS = {1: 0.40, 2: 0.40, 3: 0.20}

DEMO = [
    # (id, sector, issues): each tells a different story on stage
    ("demo-bakery-supplier", "food_supply", ["CR_EXPIRING", "DSCR_LOW", "NO_SECURITY", "RECEIVABLES_OVERDUE"]),
    ("demo-contractor", "construction", ["DSCR_LOW", "STATEMENTS_MISSING", "ACCOUNTS_MIXED"]),
    ("demo-online-store", "ecommerce", ["HISTORY_SHORT", "EINVOICING", "CASHFLOW_VOLATILE"]),
]


def _combos(rng: random.Random, n: int, n_clean: int, banned: set[frozenset[str]]) -> list[list[str]]:
    """Issue combinations with balanced coverage: rarely-used issues are favoured,
    so every issue appears about equally often."""
    out: list[list[str]] = [[] for _ in range(n_clean)]
    seen: set[frozenset[str]] = set()
    uses = {c: 0 for c in ALL_CODES}
    sizes, weights = zip(*SIZE_WEIGHTS.items())
    while len(out) < n:
        k = rng.choices(sizes, weights)[0]
        pool, picked = list(ALL_CODES), []
        for _ in range(k):
            c = rng.choices(pool, [1 / (1 + uses[x]) ** 2 for x in pool])[0]
            pool.remove(c)
            picked.append(c)
        combo = frozenset(picked)
        if combo in banned or combo in seen or not compatible(combo):
            continue
        seen.add(combo)
        for c in combo:
            uses[c] += 1
        out.append(sorted(combo))
    return out


def build() -> dict[str, list[SyntheticBusiness]]:
    dev_combos = _combos(random.Random(7), DEV_SIZE, DEV_CLEAN, banned=set())
    dev_set = {frozenset(c) for c in dev_combos if c}
    held_combos = _combos(random.Random(99), HELDOUT_SIZE, HELDOUT_CLEAN, banned=dev_set)

    dev = [make_business(f"dev-{i:03d}", 1000 + i, c) for i, c in enumerate(dev_combos)]
    held = [make_business(f"heldout-{i:03d}", 9000 + i, c) for i, c in enumerate(held_combos)]
    demo = [make_business(bid, 500 + i, iss, sector=sec) for i, (bid, sec, iss) in enumerate(DEMO)]
    return {"dev": dev, "heldout": held, "demo": demo}


def write(out_dir: Path = DATA_DIR) -> None:
    for split, businesses in build().items():
        index = []
        for b in businesses:
            folder = out_dir / split / b.meta.business_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "business.json").write_text(
                json.dumps(b.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            truth = {k: v.model_dump() for k, v in b.truth().items()}
            (folder / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
            index.append({"business_id": b.meta.business_id, "name_en": b.meta.name_en,
                          "planted_issues": b.meta.planted_issues,
                          "ready": {k: v["ready"] for k, v in truth.items()}})
        (out_dir / split / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{split:<8} {len(businesses):>3} businesses → {out_dir / split}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DATA_DIR)
    write(ap.parse_args().out)
