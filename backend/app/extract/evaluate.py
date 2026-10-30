"""How well does extraction recover the truth? Field by field, and where it matters: the verdict.

    python -m app.extract.evaluate --split dev --level realistic --reader haiku
    python -m app.extract.evaluate --split dev --level all --reader oracle      # pipeline ceiling
    python -m app.extract.evaluate --split dev --level clean --reader haiku --limit 3

Writes reports/extraction-<split>-<level>-<reader>.{json,md}.

Measured per business, against business.json (true snapshot) and noise.json (what was injected):
- field accuracy: each snapshot field within a small tolerance (only when its document was given);
- verdict agreement: the engine on the extracted snapshot gives the same ready / blockers as on
  the true one, per lender policy (this is the number that decides whether extraction is good enough);
- missing documents requested exactly; conflicts detected (recall) and none invented (false alarms);
- tokens and live latency.
Final numbers are reported on held-out only; dev is for development.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from ..engine import FinancialSnapshot, assess, available_policies, load_policy
from ..synth.dataset import DATA_DIR
from ..synth.variants import LEVELS
from .assemble import ExtractionResult, extract, make_reader

REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"

# Which document each field comes from: a field is only scored if its document was given.
SOURCE = {
    "cr_active": "cr_certificate", "cr_expiry": "cr_certificate", "operating_months": "cr_certificate",
    "monthly_revenue_sar": "bank_statement", "operating_margin": "bank_statement",
    "separate_business_account": "bank_statement",
    "existing_monthly_debt_service_sar": "credit_report", "has_active_defaults": "credit_report",
    "receivables_outstanding_sar": "receivables_aging", "receivables_overdue_90d_sar": "receivables_aging",
    "einvoicing_compliant": "tax_compliance", "vat_filed_on_time": "tax_compliance",
    "financial_statements_available": "financing_application",
    "collateral_available": "financing_application", "kafalah_guarantee": "financing_application",
    "request": "financing_application",
}


def _close(a: float, b: float, rel: float = 0.01, abs_: float = 1.0) -> bool:
    return abs(a - b) <= max(abs_, rel * abs(b))


def _revenue_ok(got: list[float], true: list[float]) -> bool:
    return len(got) == 12 and all(_close(g, t) for g, t in zip(got, true))


COMPARE: dict[str, Callable[[Any, Any], bool]] = {
    "monthly_revenue_sar": _revenue_ok,
    "operating_margin": lambda g, t: abs(g - t) <= 0.005,
    "existing_monthly_debt_service_sar": _close,
    "receivables_outstanding_sar": _close,
    "receivables_overdue_90d_sar": _close,
    "request": lambda g, t: _close(g["amount_sar"], t["amount_sar"]) and g["tenor_months"] == t["tenor_months"]
    and abs(g["annual_profit_rate"] - t["annual_profit_rate"]) < 1e-4,
}


def score_business(result: ExtractionResult, truth: FinancialSnapshot, noise: dict) -> dict[str, Any]:
    t = truth.model_dump(mode="json")
    fields: dict[str, bool | None] = {}
    for name, doc in SOURCE.items():
        if doc in noise["missing"]:
            fields[name] = None  # document not given: not scorable, counted under missing documents
            continue
        got = result.fields.get(name)
        fields[name] = got is not None and COMPARE.get(name, lambda g, tv: g == tv)(got, t[name])

    verdict: dict[str, bool | None] = {}
    if result.snapshot is not None:
        for p in available_policies():
            pol = load_policy(p)
            a, b = assess(result.snapshot, pol), assess(truth, pol)
            verdict[p] = a.ready == b.ready and set(a.blocker_codes) == set(b.blocker_codes)
    else:
        verdict = {p: None for p in available_policies()}

    true_conflicts = {c["code"] for c in noise["conflicts"]}
    found = {c.code for c in result.conflicts}
    return {
        "business_id": result.business_id,
        "fields": fields,
        "verdict": verdict,
        "snapshot_built": result.snapshot is not None,
        "missing_exact": sorted(result.missing_documents) == sorted(noise["missing"]),
        "conflicts_true": sorted(true_conflicts), "conflicts_found": sorted(found),
        "checks_failed": [c.name for c in result.checks if not c.passed],
        "usage": result.usage,
        "notes": result.notes,
    }


def _rate(xs: list[bool | None]) -> tuple[float | None, int]:
    vals = [x for x in xs if x is not None]
    return (round(sum(vals) / len(vals), 3) if vals else None), len(vals)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    field_acc = {f: _rate([r["fields"][f] for r in rows]) for f in SOURCE}
    all_fields = [v for r in rows for v in r["fields"].values()]
    verdict = {p: _rate([r["verdict"][p] for r in rows]) for p in available_policies()}
    tp = sum(len(set(r["conflicts_true"]) & set(r["conflicts_found"])) for r in rows)
    n_true = sum(len(r["conflicts_true"]) for r in rows)
    fp = sum(len(set(r["conflicts_found"]) - set(r["conflicts_true"])) for r in rows)
    usage = {k: sum(r["usage"].get(k, 0) for r in rows) for k in
             ("calls", "cache_hits", "input_tokens", "output_tokens", "live_latency_s")}
    return {
        "businesses": len(rows),
        "field_accuracy_overall": _rate(all_fields),
        "field_accuracy": field_acc,
        "verdict_agreement": verdict,
        "snapshots_built": sum(r["snapshot_built"] for r in rows),
        "missing_documents_exact": _rate([r["missing_exact"] for r in rows]),
        "conflict_recall": (round(tp / n_true, 3) if n_true else None, n_true),
        "conflict_false_alarms": fp,
        "failed_checks": {c: sum(c in r["checks_failed"] for r in rows)
                          for c in sorted({c for r in rows for c in r["checks_failed"]})},
        "usage": usage,
    }


def run(split: str, level: str, reader_kind: str, limit: int | None = None,
        only: str | None = None) -> dict[str, Any]:
    folders = sorted(p for p in (DATA_DIR / split).iterdir() if (p / "business.json").exists())
    if only:
        folders = [p for p in folders if p.name == only]
    folders = folders[:limit] if limit else folders
    rows = []
    for biz in folders:
        docs = biz / "documents" / level
        if not (docs / "noise.json").exists():
            raise SystemExit(f"No {level} documents for {biz.name}. Run: python -m app.synth.documents --split {split}")
        truth = FinancialSnapshot.model_validate(json.loads((biz / "business.json").read_text(encoding="utf-8"))["snapshot"])
        noise = json.loads((docs / "noise.json").read_text(encoding="utf-8"))
        result = extract(docs, make_reader(reader_kind, docs), biz.name)
        rows.append(score_business(result, truth, noise))
        print(f"  {biz.name:<22} fields {sum(bool(v) for v in rows[-1]['fields'].values())}/"
              f"{sum(v is not None for v in rows[-1]['fields'].values())}  verdict {rows[-1]['verdict']}", flush=True)
    return {"split": split, "level": level, "reader": reader_kind, "summary": summarise(rows), "businesses": rows}


def _pct(x: tuple[float | None, int]) -> str:
    v, n = x
    return "n/a" if v is None else f"{v:.0%} (n={n})"


def to_markdown(rep: dict[str, Any]) -> str:
    s = rep["summary"]
    out = [f"# Extraction — {rep['split']} / {rep['level']} / {rep['reader']}", "",
           f"Businesses: {s['businesses']} · snapshots built: {s['snapshots_built']}", "",
           "| Measure | Result |", "|---|---|",
           f"| Field accuracy (all fields) | {_pct(s['field_accuracy_overall'])} |"]
    for p, v in s["verdict_agreement"].items():
        out.append(f"| Verdict agreement — {p} | {_pct(v)} |")
    out += [f"| Missing documents requested exactly | {_pct(s['missing_documents_exact'])} |",
            f"| Conflict recall | {_pct(s['conflict_recall'])} |",
            f"| Conflict false alarms | {s['conflict_false_alarms']} |",
            f"| Tokens in / out | {int(s['usage']['input_tokens']):,} / {int(s['usage']['output_tokens']):,} |",
            f"| Model calls (cache hits) | {int(s['usage']['calls'])} ({int(s['usage']['cache_hits'])}) |",
            f"| Live latency | {s['usage']['live_latency_s']} s |", "",
            "## Field accuracy", "", "| Field | Accuracy |", "|---|---|"]
    out += [f"| {f} | {_pct(v)} |" for f, v in s["field_accuracy"].items()]
    if s["failed_checks"]:
        out += ["", "## Failed self-checks", ""] + [f"- {c}: {n} businesses" for c, n in s["failed_checks"].items()]
    wrong = [(r["business_id"], [f for f, v in r["fields"].items() if v is False]) for r in rep["businesses"]]
    wrong = [w for w in wrong if w[1]]
    if wrong:
        out += ["", "## Wrong fields by business", ""] + [f"- {b}: {', '.join(fs)}" for b, fs in wrong]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "heldout", "demo"], default="dev")
    ap.add_argument("--level", choices=[*LEVELS, "all"], default="realistic")
    ap.add_argument("--reader", choices=["haiku", "oracle"], default="haiku")
    ap.add_argument("--limit", type=int, help="only the first N businesses (cheap trial runs)")
    ap.add_argument("--business", help="only this business id")
    args = ap.parse_args()
    if args.split == "heldout":
        print("Held-out: final numbers only. Do not tune on these results.")
    REPORT_DIR.mkdir(exist_ok=True)
    for level in (LEVELS if args.level == "all" else [args.level]):
        print(f"{args.split} / {level} / {args.reader}")
        rep = run(args.split, level, args.reader, args.limit, args.business)
        stem = f"extraction-{args.split}-{level}-{args.reader}" + (f"-first{args.limit}" if args.limit else "")
        (REPORT_DIR / f"{stem}.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
        (REPORT_DIR / f"{stem}.md").write_text(to_markdown(rep), encoding="utf-8")
        s = rep["summary"]
        print(f"  => fields {_pct(s['field_accuracy_overall'])}, verdict "
              + ", ".join(f"{p} {_pct(v)}" for p, v in s["verdict_agreement"].items())
              + f", report: reports/{stem}.md")


if __name__ == "__main__":
    main()
