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
from .injection import strip_instructions
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


class EmbeddedInstruction(BaseModel):
    document: str
    text: str
    found_by: str  # "detector" (removed before the model saw it) or "model" (reported in notes)


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
    embedded_instructions: list[EmbeddedInstruction] = []  # prompt injection attempts found
    usage: dict[str, float]


def _d(x: str | None) -> date | None:
    try:
        return date.fromisoformat(x) if x else None
    except ValueError:
        return None


def _name_key(name: str | None) -> str:
    """Letters only, lower case: "Khalid Al-Harbi", "KHALID ALHARBI" and "khalid alharbi" all match.
    Arabic letters are kept, so the Arabic name matches its own spelling."""
    return "".join(ch for ch in (name or "").lower() if ch.isalpha())


def is_owner(counterparty: str | None, owner_names: list[str | None]) -> bool:
    """Is this counterparty the business owner? Bank abbreviations may cut a long name,
    so a counterparty of at least 8 letters that starts the owner's name also counts."""
    cp = _name_key(counterparty)
    if len(cp) < 6:
        return False
    for name in owner_names:
        key = _name_key(name)
        if key and (cp == key or key in cp or (len(cp) >= 8 and key.startswith(cp))):
            return True
    return False


INFLOW = ("revenue", "owner_funds")
OUTFLOW = ("opex", "debt_service", "personal")


def repair_bank(bank: dict) -> dict[str, int]:
    """Fix each line's direction from the running balance printed on the statement, in place.

    The model sometimes reads money in as money out (most often in right-to-left layouts).
    The statement prints the balance after every line, so the direction is certain: if the
    balance went up by the amount, money came in. Then a category that contradicts the
    direction is corrected (money in cannot be a cost). Returns counts for the notes."""
    txns = bank.get("transactions") or []
    prev = bank.get("opening_balance")
    flipped = recategorised = mismatched = 0
    for t in txns:
        amount = float(t.get("amount") or 0)
        bal = t.get("balance")
        if prev is not None and bal is not None:
            delta = round(float(bal) - float(prev), 2)
            if abs(abs(delta) - abs(amount)) <= 0.05:
                if delta and (delta > 0) != (amount > 0):
                    t["amount"] = amount = -amount
                    flipped += 1
            else:
                mismatched += 1  # amount or balance misread: left as read, the reconciliation check reports it
        prev = float(bal) if bal is not None else (float(prev) + amount if prev is not None else None)
        cat = t.get("category")
        if amount > 0 and cat in OUTFLOW:
            t["category"] = "revenue"  # money in is never a cost; the owner rule below may still move it
            recategorised += 1
        elif amount < 0 and cat in INFLOW:
            t["category"] = "other"
            recategorised += 1
    return {"flipped": flipped, "recategorised": recategorised, "mismatched": mismatched}


def bank_gap(bank: dict) -> float | None:
    """opening + all lines - closing, after repair; None if the balances are missing."""
    opening, closing = bank.get("opening_balance"), bank.get("closing_balance")
    if opening is None or closing is None:
        return None
    return round(opening + sum(float(t.get("amount") or 0) for t in bank.get("transactions") or []) - closing, 2)


def _named_person(counterparty: str | None) -> bool:
    """A counterparty that reads as a person's name (two or more words, not a generic label)."""
    cp = (counterparty or "").strip().lower()
    generic = ("owner", "المالك", "capital", "رأس مال", "cash", "نقد")
    return len(cp.split()) >= 2 and not any(g in cp for g in generic)


def _month_starts(as_of: date) -> list[tuple[int, int]]:
    out, y, m = [], as_of.year, as_of.month
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def read_all(docs: DocumentSet, reader: Reader, log: CallLog,
             found: list[EmbeddedInstruction] | None = None) -> tuple[dict[str, dict], list[str]]:
    readings: dict[str, dict] = {}
    unreadable: list[str] = []
    context: dict[str, str | None] = {}
    found = found if found is not None else []
    for name in READ_ORDER:
        if name in docs.texts:
            text, removed = strip_instructions(docs.texts[name])
            found += [EmbeddedInstruction(document=name, text=t, found_by="detector") for t in removed]
            doc = DocInput(name, text=text)
        elif name in docs.scanned:
            doc = DocInput(name, pdf_path=docs.scanned[name])
        else:
            continue
        try:
            r = reader.read(doc, context)
        except ReadError:
            if name != "bank_statement" or doc.text is None:
                unreadable.append(name)
                continue
            r = None
        if r is not None:
            log.calls.append(r.record)
            r.fields = sanitize(name, r.fields)
        if name == "bank_statement" and doc.text is not None:
            fields = _bank_with_fallback(r.fields if r else None, doc.text, reader, context, log)
            if fields is None:
                unreadable.append(name)
                continue
            readings[name] = fields
        else:
            readings[name] = r.fields
        if name == "cr_certificate":
            context["owner_name"] = r.fields.get("owner_name")
            context["owner_name_ar"] = r.fields.get("owner_name_ar")
        if name == "credit_report":
            lenders = [f.get("lender") for f in r.fields.get("facilities") or [] if f.get("lender")]
            context["lenders"] = ", ".join(lenders) or None
    return readings, unreadable


LIST_FIELDS = {"bank_statement": "transactions", "credit_report": "facilities", "tax_compliance": "vat_returns"}


def sanitize(name: str, fields: Any) -> dict:
    """Make a reading safe to compute on, whatever shape the model returned: a list item that
    is not an object (e.g. a line as plain text) is dropped and noted, never crashes the run.
    A dropped bank line then shows up in the reconciliation check."""
    if not isinstance(fields, dict):
        return {"notes": [f"[{name}] the reader returned no structured fields"]}
    key = LIST_FIELDS.get(name)
    if key is not None:
        items = fields.get(key)
        items = items if isinstance(items, list) else []
        kept = [i for i in items if isinstance(i, dict)]
        if len(kept) != len(items):
            fields.setdefault("notes", [])
            if isinstance(fields["notes"], list):
                fields["notes"].append(f"{len(items) - len(kept)} malformed {key} item(s) dropped")
        fields[key] = kept
    if not isinstance(fields.get("notes"), list):
        fields["notes"] = []
    fields["notes"] = [n for n in fields["notes"] if isinstance(n, str)]
    return fields


def _bank_with_fallback(fields: dict | None, text: str, reader: Reader, context: dict, log: CallLog) -> dict | None:
    """If a whole-statement reading does not reconcile even after repair (lines dropped or
    misread, or the answer cut off), read the statement again one page at a time and keep the
    reading that reconciles better. Costs extra calls only for the statements that need it."""
    import copy

    def gap(f: dict | None) -> float:
        if not f:
            return float("inf")
        f = copy.deepcopy(f)
        repair_bank(f)
        g = bank_gap(f)
        return abs(g) if g is not None else float("inf")

    if gap(fields) < 0.05:
        return fields
    pages = [p for p in text.split("--- page ")[1:] if p.strip()]
    if len(pages) < 2:
        return fields
    merged: dict | None = None
    for i, body in enumerate(pages, 1):
        try:
            r = reader.read(DocInput("bank_statement", text="--- page " + body), {**context, "page": f"{i} of {len(pages)}"})
        except ReadError:
            return fields
        log.calls.append(r.record)
        r.fields = sanitize("bank_statement", r.fields)
        if merged is None:
            merged = dict(r.fields)
            merged["transactions"] = list(r.fields.get("transactions") or [])
            merged["notes"] = list(r.fields.get("notes") or [])
        else:
            merged["transactions"] += r.fields.get("transactions") or []
            merged["notes"] += r.fields.get("notes") or []
            for k in ("closing_balance", "period_end", "account_type", "period_start", "opening_balance"):
                if r.fields.get(k) is not None and (k == "closing_balance" or merged.get(k) is None):
                    merged[k] = r.fields[k]
    if merged is not None and gap(merged) < gap(fields):
        merged["notes"].append("Read page by page: the whole-statement reading did not reconcile.")
        return merged
    return fields


def assemble(business_id: str, docs: DocumentSet, readings: dict[str, dict],
             unreadable: list[str], log: CallLog,
             found: list[EmbeddedInstruction] | None = None) -> ExtractionResult:
    f: dict[str, Any] = {}
    conflicts: list[DetectedConflict] = []
    checks: list[Check] = []
    notes = [f"[{doc}] {n}" for doc, r in readings.items() for n in (r.get("notes") or [])]
    found = list(found or [])
    for doc, r in readings.items():  # the model reports instructions it saw (scanned pages included)
        for n in r.get("notes") or []:
            if n.upper().startswith("INSTRUCTION IN DOCUMENT"):
                found.append(EmbeddedInstruction(document=doc, text=n, found_by="model"))

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
        fix = repair_bank(bank)
        if fix["flipped"] or fix["recategorised"]:
            notes.append(f"[assemble] direction corrected from the running balance on {fix['flipped']} line(s); "
                         f"{fix['recategorised']} category(ies) made consistent with the direction.")
        # Business rule, applied in Python rather than trusted to the model: money coming in
        # from the owner's own name is the owner's money, not revenue (found by error analysis:
        # the reader's only mistakes on dev were exactly these lines).
        owners = [cr.get("owner_name"), cr.get("owner_name_ar")]
        moved = back = 0
        owner_known = any(owners)
        for t in txns:
            cp = t.get("counterparty")
            incoming = float(t.get("amount") or 0) > 0
            if t.get("category") in ("revenue", "other") and incoming and is_owner(cp, owners):
                t["category"] = "owner_funds"
                moved += 1
            elif t.get("category") == "owner_funds" and incoming and owner_known and _named_person(cp) \
                    and not is_owner(cp, owners):
                t["category"] = "revenue"  # a transfer from someone else, by name, is not the owner's money
                back += 1
        if moved:
            notes.append(f"[assemble] {moved} incoming transfer(s) from the owner's own name counted as owner funds, not revenue.")
        if back:
            notes.append(f"[assemble] {back} transfer(s) from people other than the owner counted as revenue, not owner funds.")
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

    checks.append(Check(name="NO_EMBEDDED_INSTRUCTIONS", passed=not found,
                        detail="none found" if not found else
                        f"{len(found)} instruction(s) aimed at an AI reader in: "
                        + ", ".join(sorted({f.document for f in found}))))

    missing = list(docs.missing)
    needed = [k for k in FinancialSnapshot.model_fields if k != "business_id"]
    unresolved = [k for k in needed if f.get(k) is None]
    # Safety rule: never decide on a bank statement that does not add up. Better to say
    # "needs a person or a clearer copy" than to give a lender a wrong number.
    if any(c.name == "BALANCE_RECONCILES" and not c.passed for c in checks):
        for k in ("monthly_revenue_sar", "operating_margin"):
            if k not in unresolved:
                unresolved.append(k)
        if "bank_statement" not in unreadable:
            unreadable = [*unreadable, "bank_statement"]
        notes.append("[assemble] the bank statement does not reconcile even after re-reading; "
                     "no decision is made on it (human review or a clearer copy needed).")
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
        conflicts=conflicts, checks=checks, notes=notes, embedded_instructions=found, usage=log.summary(),
    )


def extract(folder: Path, reader: Reader, business_id: str | None = None) -> ExtractionResult:
    """Read and assemble one business. `folder` holds its PDFs (one difficulty level)."""
    bid = business_id or _business_id(folder)
    docs = load_documents(folder)
    log, found = CallLog(), []
    readings, unreadable = read_all(docs, reader, log, found)
    return assemble(bid, docs, readings, unreadable, log, found)


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
    ap.add_argument("--out", type=Path, help="write the JSON to this file (UTF-8; safer than > on Windows)")
    args = ap.parse_args()
    result = extract(args.folder, make_reader(args.reader, args.folder))
    text = json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        ok = {c.name: c.passed for c in result.checks}
        print(f"wrote {args.out} · snapshot {'built' if result.snapshot else 'NOT built'} · checks {ok} · "
              f"usage {result.usage}")
    else:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()


__all__ = ["ExtractionResult", "extract", "assemble", "read_all", "REQUIRED_DOCS", "OPTIONAL_DOCS"]
