"""From a folder of documents to a `FinancialSnapshot`: read each document with the
model, then do every sum, average and comparison in Python.

    python -m app.extract.assemble <documents_folder> [--reader haiku|oracle]

Order matters: the CR certificate and credit report are read first, because the bank
statement reader needs the owner's name (a transfer from the owner is the owner's money,
not revenue) and the lenders' names.

Never guesses: a missing required document leaves its fields unresolved and no snapshot
is built; the result lists what to request. Documents that disagree are reported as
conflicts, and the authoritative source wins (CR for dates, bank statement for revenue).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ..engine import FinancialSnapshot
from .llm import CallLog, DocInput, Reader, ReadError
from .pdf_text import OPTIONAL_DOCS, REQUIRED_DOCS, DocumentSet, load_documents

READ_ORDER = ("cr_certificate", "credit_report", "bank_statement", "financing_application",
              "receivables_aging", "tax_compliance", "income_statement")

REVENUE_TOLERANCE = 0.02  # income statement vs bank statement revenue
DEBT_TOLERANCE = 0.05     # credit report instalments vs instalments paid in the bank statement


class DetectedConflict(BaseModel):
    code: str
    documents: list[str]
    shown: str
    used: str
    message: str


class Check(BaseModel):
    name: str
    passed: bool
    detail: str


class ExtractionResult(BaseModel):
    business_id: str
    snapshot: FinancialSnapshot | None
    fields: dict[str, Any]            # every value we could resolve, even without a full snapshot
    missing_documents: list[str]      # required and absent: request them
    unreadable_documents: list[str]   # present, but the reader failed
    unresolved_fields: list[str]
    conflicts: list[DetectedConflict]
    checks: list[Check]
    notes: list[str]                  # the model's remarks for an analyst; never change values
    usage: dict[str, float]


def _d(x: str | None) -> date | None:
    try:
        return date.fromisoformat(x) if x else None
    except ValueError:
        return None


def _month_starts(as_of: date) -> list[tuple[int, int]]:
    out, y, m = [], as_of.year, as_of.month
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def read_all(docs: DocumentSet, reader: Reader, log: CallLog) -> tuple[dict[str, dict], list[str]]:
    readings: dict[str, dict] = {}
    unreadable: list[str] = []
    context: dict[str, str | None] = {}
    for name in READ_ORDER:
        if name in docs.texts:
            doc = DocInput(name, text=docs.texts[name])
        elif name in docs.scanned:
            doc = DocInput(name, pdf_path=docs.scanned[name])
        else:
            continue
        try:
            r = reader.read(doc, context)
        except ReadError:
            unreadable.append(name)
            continue
        log.calls.append(r.record)
        readings[name] = r.fields
        if name == "cr_certificate":
            context["owner_name"] = r.fields.get("owner_name")
            context["owner_name_ar"] = r.fields.get("owner_name_ar")
        if name == "credit_report":
            lenders = [f.get("lender") for f in r.fields.get("facilities") or [] if f.get("lender")]
            context["lenders"] = ", ".join(lenders) or None
    return readings, unreadable


def assemble(business_id: str, docs: DocumentSet, readings: dict[str, dict],
             unreadable: list[str], log: CallLog) -> ExtractionResult:
    f: dict[str, Any] = {}
    conflicts: list[DetectedConflict] = []
    checks: list[Check] = []
    notes = [f"[{doc}] {n}" for doc, r in readings.items() for n in (r.get("notes") or [])]

    cr = readings.get("cr_certificate", {})
    credit = readings.get("credit_report")
    bank = readings.get("bank_statement")
    app = readings.get("financing_application", {})
    aging = readings.get("receivables_aging")
    tax = readings.get("tax_compliance")
    income = readings.get("income_statement")

    as_of = _d(bank.get("period_end")) if bank else None
    as_of = as_of or (_d(credit.get("report_date")) if credit else None)
    f["as_of"] = as_of

    # --- registration (CR is the authority on dates) ---
    issue, expiry = _d(cr.get("issue_date")), _d(cr.get("expiry_date"))
    f["cr_active"] = cr.get("status_active")
    f["cr_expiry"] = expiry
    if issue and as_of:
        f["operating_months"] = round((as_of - issue).days / 30.44)
    claimed = _d(app.get("operating_since"))
    if claimed and issue and claimed != issue:
        conflicts.append(DetectedConflict(
            code="APP_OPERATING_SINCE", documents=["financing_application", "cr_certificate"],
            shown=claimed.isoformat(), used=issue.isoformat(),
            message=f"Application says operating since {claimed}, the CR was issued {issue}; using the CR."))

    # --- bank statement: revenue, margin, account type ---
    bank_revenue = None
    if bank and as_of:
        txns = bank.get("transactions") or []
        by_month: dict[tuple[int, int], float] = defaultdict(float)
        opex = debt_paid = 0.0
        for t in txns:
            day = _d(t.get("date"))
            amt = float(t.get("amount") or 0)
            cat = t.get("category")
            if cat == "revenue" and day:
                by_month[(day.year, day.month)] += amt
            elif cat == "opex":
                opex -= amt
            elif cat == "debt_service":
                debt_paid -= amt
        months = _month_starts(as_of)
        f["monthly_revenue_sar"] = [round(by_month[m], 2) for m in months]
        bank_revenue = sum(f["monthly_revenue_sar"])
        if bank_revenue > 0:
            f["operating_margin"] = round(min(max(1 - opex / bank_revenue, 0.0), 1.0), 4)
        acct = bank.get("account_type")
        f["separate_business_account"] = None if acct is None else acct == "business"

        opening, closing = bank.get("opening_balance"), bank.get("closing_balance")
        if opening is not None and closing is not None:
            gap = opening + sum(float(t.get("amount") or 0) for t in txns) - closing
            checks.append(Check(name="BALANCE_RECONCILES", passed=abs(gap) < 0.05,
                                detail=f"opening + lines - closing = {gap:,.2f} SAR over {len(txns)} lines"))
        empty = [f"{y}-{m:02d}" for (y, m) in months if not any(
            (d := _d(t.get("date"))) and (d.year, d.month) == (y, m) for t in txns)]
        checks.append(Check(name="TWELVE_MONTHS_COVERED", passed=not empty,
                            detail="all 12 months have lines" if not empty else f"no lines in {', '.join(empty)}"))
        f["_debt_paid_monthly"] = round(debt_paid / 12, 2)

    # --- credit report: existing debt and defaults ---
    if credit is not None:
        facs = credit.get("facilities") or []
        f["existing_monthly_debt_service_sar"] = round(sum(
            float(x.get("monthly_instalment") or 0) for x in facs if x.get("status") == "regular"), 2)
        f["has_active_defaults"] = any(x.get("status") == "default" for x in facs)
        paid = f.get("_debt_paid_monthly")
        if paid is not None:
            listed = f["existing_monthly_debt_service_sar"]
            ok = abs(paid - listed) <= max(1.0, DEBT_TOLERANCE * listed)
            checks.append(Check(name="DEBT_MATCHES_BANK", passed=ok,
                                detail=f"credit report SAR {listed:,.2f}/month, bank statement SAR {paid:,.2f}/month"))
    f.pop("_debt_paid_monthly", None)

    # --- receivables, tax, statements ---
    if aging is not None:
        f["receivables_outstanding_sar"] = aging.get("total_outstanding")
        f["receivables_overdue_90d_sar"] = aging.get("overdue_90_plus")
    if tax is not None:
        f["einvoicing_compliant"] = tax.get("einvoicing_integrated")
        returns = tax.get("vat_returns") or []
        pairs = [(_d(r.get("due_date")), _d(r.get("filed_date"))) for r in returns]
        if returns and all(due and filed for due, filed in pairs):
            f["vat_filed_on_time"] = all(filed <= due for due, filed in pairs)
    f["financial_statements_available"] = "income_statement" in readings or "income_statement" in docs.scanned
    if income and bank_revenue:
        rev = income.get("revenue")
        if rev is not None and abs(rev - bank_revenue) > REVENUE_TOLERANCE * bank_revenue:
            code = "INCOME_REVENUE_INFLATED" if rev > bank_revenue else "INCOME_REVENUE_UNDERSTATED"
            conflicts.append(DetectedConflict(
                code=code, documents=["income_statement", "bank_statement"],
                shown=f"{rev:.2f}", used=f"{bank_revenue:.2f}",
                message=f"Income statement revenue SAR {rev:,.0f} vs SAR {bank_revenue:,.0f} received in the "
                        f"bank statement ({rev / bank_revenue - 1:+.0%}); using the bank statement."))

    # --- the request and its security ---
    if app:
        f["collateral_available"] = app.get("collateral_offered")
        f["kafalah_guarantee"] = app.get("kafalah_guarantee")
        if app.get("requested_amount") and app.get("tenor_months") and app.get("annual_profit_rate") is not None:
            f["request"] = {"amount_sar": app["requested_amount"], "tenor_months": app["tenor_months"],
                            "annual_profit_rate": app["annual_profit_rate"]}

    missing = list(docs.missing)
    needed = [k for k in FinancialSnapshot.model_fields if k != "business_id"]
    unresolved = [k for k in needed if f.get(k) is None]
    snapshot = None
    if not missing and not unresolved:
        try:
            snapshot = FinancialSnapshot(business_id=business_id, **{k: f[k] for k in needed})
        except ValidationError as e:
            notes.append(f"[assemble] values failed validation: {e.errors()[0]['msg']}")
            unresolved = sorted({str(err["loc"][0]) for err in e.errors()})

    return ExtractionResult(
        business_id=business_id, snapshot=snapshot,
        fields={k: (v.isoformat() if isinstance(v, date) else v) for k, v in f.items()},
        missing_documents=missing, unreadable_documents=unreadable, unresolved_fields=unresolved,
        conflicts=conflicts, checks=checks, notes=notes, usage=log.summary(),
    )


def extract(folder: Path, reader: Reader, business_id: str | None = None) -> ExtractionResult:
    """Read and assemble one business. `folder` holds its PDFs (one difficulty level)."""
    bid = business_id or _business_id(folder)
    docs = load_documents(folder)
    log = CallLog()
    readings, unreadable = read_all(docs, reader, log)
    return assemble(bid, docs, readings, unreadable, log)


def _business_id(folder: Path) -> str:
    # data/<split>/<business_id>/documents/<level>
    parts = folder.resolve().parts
    return parts[-3] if len(parts) >= 3 and parts[-2] == "documents" else folder.name


def make_reader(kind: str, folder: Path | None = None) -> Reader:
    from .llm import AnthropicReader, CachedReader

    if kind == "haiku":
        return CachedReader(AnthropicReader())
    if kind == "oracle":
        from .oracle import OracleReader
        return OracleReader.for_folder(folder)
    raise ValueError(f"unknown reader {kind}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--reader", choices=["haiku", "oracle"], default="haiku")
    args = ap.parse_args()
    result = extract(args.folder, make_reader(args.reader, args.folder))
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = ["ExtractionResult", "extract", "assemble", "read_all", "REQUIRED_DOCS", "OPTIONAL_DOCS"]
