"""A reader that knows the answers: it reads from the ledger instead of the PDF.

Two uses, both without an API key:
1. The pipeline ceiling. With a perfect reader, assemble + evaluate must reproduce
   the true snapshot exactly; anything less is a bug in OUR code, not the model's.
2. Checking the evaluation itself. `mistakes` plants known reading errors
   (e.g. the owner's transfer counted as revenue) and the report must catch them.

It answers what the DOCUMENTS say, including their conflicting values, so conflict
detection is tested too.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..synth.generator import SyntheticBusiness
from ..synth.ledger import build_ledger
from ..synth.variants import Level, conflict_value, plan_noise
from .llm import CallRecord, DocInput, Reading

CATEGORY = {"revenue": "revenue", "opex": "opex", "debt": "debt_service", "owner": "owner_funds",
            "personal": "personal"}
MISTAKES = {
    "owner_as_revenue": "the owner's own transfers counted as revenue",
    "personal_as_opex": "personal spending counted as business costs",
    "drop_last_line": "the last statement line skipped",
    "debit_credit_swap_first_line": "the first line's direction reversed",
}


class OracleReader:
    model = "oracle"

    def __init__(self, business: SyntheticBusiness, level: Level, mistakes: frozenset[str] = frozenset()):
        unknown = set(mistakes) - set(MISTAKES)
        if unknown:
            raise ValueError(f"unknown mistakes: {unknown}")
        self.b, self.plan, self.mistakes = business, plan_noise(business, level), mistakes
        self.L = build_ledger(business)

    @classmethod
    def for_folder(cls, folder: Path, mistakes: frozenset[str] = frozenset()) -> "OracleReader":
        folder = folder.resolve()
        b = SyntheticBusiness.model_validate(
            json.loads((folder.parent.parent / "business.json").read_text(encoding="utf-8")))
        return cls(b, folder.name, mistakes)  # type: ignore[arg-type]

    def read(self, doc: DocInput, context: dict[str, str | None]) -> Reading:
        fields = getattr(self, f"_{doc.name}")()
        fields["notes"] = []
        return Reading(fields, CallRecord(doc.name, self.model, 0, 0, 0.0, False))

    # --- one method per document, values as the document prints them ---

    def _cr_certificate(self):
        s = self.b.snapshot
        return {"business_name": self.b.meta.name_en, "cr_number": self.L.cr_number,
                "owner_name": self.plan.owner_en, "owner_name_ar": self.plan.owner_ar,
                "issue_date": self.L.cr_issue_date.isoformat(), "expiry_date": s.cr_expiry.isoformat(),
                "status_active": s.cr_active}

    def _credit_report(self):
        return {"report_date": self.b.snapshot.as_of.isoformat(), "facilities": [
            {"lender": f.lender_en, "facility_type": f.kind_en,
             "monthly_instalment": f.instalment / 100 if f.instalment else None,
             "outstanding": f.outstanding / 100, "status": f.status} for f in self.L.facilities]}

    def _bank_statement(self):
        rows = []
        for t in self.L.statement:
            cat = CATEGORY[t.category]
            if cat == "owner_funds" and "owner_as_revenue" in self.mistakes:
                cat = "revenue"
            if cat == "personal" and "personal_as_opex" in self.mistakes:
                cat = "opex"
            rows.append({"date": t.day.isoformat(), "amount": (t.credit - t.debit) / 100,
                         "category": cat, "counterparty": t.party_en or None})
        if "debit_credit_swap_first_line" in self.mistakes:
            rows[0]["amount"] = -rows[0]["amount"]
        if "drop_last_line" in self.mistakes:
            rows = rows[:-1]
        return {"account_type": self.L.account_type,
                "period_start": self.L.month_starts[0].isoformat(),
                "period_end": self.b.snapshot.as_of.isoformat(),
                "opening_balance": self.L.opening_balance / 100,
                "closing_balance": self.L.statement[-1].balance / 100, "transactions": rows}

    def _receivables_aging(self):
        total = sum(a + b + c + o for _, _, a, b, c, o in self.L.aging)
        over = sum(o for *_, o in self.L.aging)
        return {"as_of": self.b.snapshot.as_of.isoformat(), "total_outstanding": total / 100,
                "overdue_90_plus": over / 100}

    def _tax_compliance(self):
        return {"einvoicing_integrated": self.b.snapshot.einvoicing_compliant, "vat_returns": [
            {"period": p, "due_date": due.isoformat(), "filed_date": filed.isoformat()}
            for p, due, filed in self.L.vat_returns]}

    def _financing_application(self):
        s, r = self.b.snapshot, self.b.snapshot.request
        return {"requested_amount": r.amount_sar, "tenor_months": r.tenor_months,
                "annual_profit_rate": r.annual_profit_rate, "collateral_offered": s.collateral_available,
                "kafalah_guarantee": s.kafalah_guarantee,
                "operating_since": conflict_value(self.plan, "APP_OPERATING_SINCE") or self.L.cr_issue_date.isoformat(),
                "financial_statements_attached": s.financial_statements_available}

    def _income_statement(self):
        rev = sum(t.credit for t in self.L.statement if t.category == "revenue") / 100
        opex = sum(t.debit for t in self.L.statement if t.category == "opex") / 100
        shown = conflict_value(self.plan, "INCOME_REVENUE_INFLATED")
        return {"period_start": self.L.month_starts[0].isoformat(), "period_end": self.b.snapshot.as_of.isoformat(),
                "revenue": float(shown) if shown else rev, "operating_expenses": opex}
