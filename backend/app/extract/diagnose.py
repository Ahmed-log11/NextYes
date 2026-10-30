"""Where exactly did the reader go wrong on a bank statement? Line by line, against the truth.

    python -m app.extract.diagnose dev-001 --level realistic
    python -m app.extract.diagnose dev-002 --level realistic --reader oracle
    python -m app.extract.diagnose dev-028 --out diag-dev-028.txt          # UTF-8 file (Arabic stays readable)

Uses the cached readings (free after an evaluation run). If a required document is missing,
it is added from the clean level first, exactly as the evaluation does. Prints:
- how many lines the reader returned vs the statement;
- a confusion table: true category x category the reader chose;
- every line where the category or the sign is wrong, with the text the document printed;
- revenue per month: read vs true.
Error analysis like this decides the next prompt version (see PROMPT_VERSION in schemas.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from ..synth.dataset import DATA_DIR
from ..synth.generator import SyntheticBusiness
from ..synth.ledger import build_ledger
from ..synth.variants import plan_noise, reword
from .assemble import make_reader, read_all
from .llm import CallLog
from .oracle import CATEGORY
from .pdf_text import load_documents


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("business_id")
    ap.add_argument("--level", default="realistic", choices=["clean", "realistic", "hard"])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--reader", default="haiku", choices=["haiku", "oracle"])
    ap.add_argument("--out", type=Path, help="write to this UTF-8 file instead of the console")
    args = ap.parse_args()
    if args.out:
        sys.stdout = open(args.out, "w", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")

    biz = DATA_DIR / args.split / args.business_id
    b = SyntheticBusiness.model_validate(json.loads((biz / "business.json").read_text(encoding="utf-8")))
    plan = plan_noise(b, args.level)
    L = build_ledger(b)
    printed = reword(L, plan)

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / args.level
        shutil.copytree(biz / "documents" / args.level, folder)
        for name in plan.missing:
            shutil.copy(biz / "documents" / "clean" / f"{name}.pdf", folder / f"{name}.pdf")
        if args.reader == "oracle":
            from .oracle import OracleReader
            reader = OracleReader(b, args.level)  # type: ignore[arg-type]
        else:
            reader = make_reader("haiku", folder)
        log = CallLog()
        readings, _ = read_all(load_documents(folder), reader, log)

    import copy

    from .assemble import is_owner, repair_bank

    raw_bank = readings.get("bank_statement", {})
    fixed_bank = copy.deepcopy(raw_bank)
    repair_bank(fixed_bank)
    cr = readings.get("cr_certificate", {})
    for t in fixed_bank.get("transactions") or []:
        if t.get("category") in ("revenue", "other") and float(t.get("amount") or 0) > 0 \
                and is_owner(t.get("counterparty"), [cr.get("owner_name"), cr.get("owner_name_ar")]):
            t["category"] = "owner_funds"
    raw_rows = raw_bank.get("transactions") or []
    rows = fixed_bank.get("transactions") or []
    print(f"{args.business_id} / {args.level} · bank layout: {plan.bank_format} · "
          f"Arabic-only share {plan.arabic_only_share} · owner: {plan.owner_en}")
    print(f"lines: read {len(rows)}, statement {len(L.statement)} · calls {log.summary()}")

    # align by position when counts match, else by (date, amount)
    truth = [(t.day.isoformat(), round((t.credit - t.debit) / 100, 2), CATEGORY[t.category], en, ar)
             for t, en, ar in printed]
    if len(rows) == len(truth):
        pairs = list(zip(truth, rows))
    else:
        pool = defaultdict(list)
        for r in rows:
            pool[(r.get("date"), round(float(r.get("amount") or 0), 2))].append(r)
        pairs = [(t, (pool[(t[0], t[1])] or [None]).pop(0) if pool[(t[0], t[1])] else None) for t in truth]

    confusion = Counter()
    wrong = []
    for (date, amount, cat, en, ar), r in pairs:
        if r is None:
            wrong.append((date, amount, cat, "MISSING", en, ar))
            continue
        got_cat, got_amt = r.get("category"), round(float(r.get("amount") or 0), 2)
        confusion[(cat, got_cat)] += 1
        if got_cat != cat or got_amt != amount:
            wrong.append((date, amount, cat, f"{got_cat} {got_amt:+,.2f}" if got_amt != amount else got_cat, en, ar))

    cats = sorted({c for c, _ in confusion} | {g for _, g in confusion}, key=str)
    print("\nconfusion (rows = true category, columns = reader's choice):")
    print(" " * 14 + "".join(f"{str(c)[:11]:>12}" for c in cats))
    for t in cats:
        print(f"{str(t)[:13]:<14}" + "".join(f"{confusion[(t, g)] or '':>12}" for g in cats))

    def count_wrong(rs):
        n = 0
        for (date, amount, cat, *_), r in zip(truth, rs):
            n += r.get("category") != cat or round(float(r.get("amount") or 0), 2) != amount
        return n + abs(len(rs) - len(truth))

    print(f"\nwrong lines as the model read them: {count_wrong(raw_rows)} · after the Python fixes "
          f"(direction from balance, owner rule): {len(wrong)}")
    print("lines still wrong after the fixes:")
    for date, amount, cat, got, en, ar in wrong:
        text = en if en else ar
        print(f"  {date}  {amount:>+13,.2f}  true {cat:<12} read {got:<22} | {text}")

    by_true, by_read = defaultdict(float), defaultdict(float)
    for (date, amount, cat, *_), r in pairs:
        if cat == "revenue":
            by_true[date[:7]] += amount
        if r is not None and r.get("category") == "revenue":
            by_read[(r.get("date") or "")[:7]] += float(r.get("amount") or 0)
    print("\nrevenue by month (read vs true):")
    for m in sorted(by_true):
        diff = by_read[m] - by_true[m]
        print(f"  {m}  {by_read[m]:>14,.2f}  {by_true[m]:>14,.2f}  {'' if abs(diff) < 1 else f'diff {diff:+,.2f}'}")


if __name__ == "__main__":
    main()
