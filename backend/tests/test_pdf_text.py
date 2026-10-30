"""The PDF reader must hand the model text it can trust: right columns, readable Arabic."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from app.extract.pdf_text import REQUIRED_DOCS, load_documents, read_pdf
from app.synth.dataset import build
from app.synth.documents import render_all
from app.synth.ledger import build_ledger

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"
ALL = {b.meta.business_id: b for split in build().values() for b in split}


def _hardest() -> list:
    """Businesses with the longest table text: several facilities, a default, a personal account."""
    picks = [b for b in ALL.values() if b.snapshot.has_active_defaults and not b.snapshot.separate_business_account]
    picks += [b for b in ALL.values() if b.snapshot.existing_monthly_debt_service_sar > 0][:2]
    picks += [ALL["demo-bakery-supplier"]]
    return picks[:5]


@pytest.fixture(scope="module", params=_hardest(), ids=lambda b: b.meta.business_id)
def rendered(request, tmp_path_factory):
    b = request.param
    folder = tmp_path_factory.mktemp(b.meta.business_id)
    render_all(b, folder)
    return b, load_documents(folder)


def test_statement_amounts_stay_in_their_column(rendered):
    """Every amount must sit nearer its own header (Debit or Credit) than the other one,
    or a reader cannot tell money in from money out."""
    b, docs = rendered
    lines = docs.texts["bank_statement"].splitlines()
    header = next(l for l in lines if "Debit" in l and "Credit" in l)
    debit_end = header.index("Debit") + len("Debit / مدين")
    credit_end = header.index("Credit") + len("Credit / دائن")
    rows = [l for l in lines if re.match(r"\s*\d{4}-\d{2}-\d{2}\s", l)]
    ledger = build_ledger(b)
    assert len(rows) == len(ledger.statement)

    for line, txn in zip(rows, ledger.statement):
        amounts = list(re.finditer(r"\d{1,3}(?:,\d{3})*\.\d{2}", line))
        assert len(amounts) == 2, line  # the movement, then the balance
        end = amounts[0].end()
        side = "debit" if abs(end - debit_end) < abs(end - credit_end) else "credit"
        assert side == ("debit" if txn.debit else "credit"), line


def test_arabic_reads_in_logical_order(rendered):
    b, docs = rendered
    cr = docs.texts["cr_certificate"]
    assert b.meta.name_ar in cr  # includes a lam-alef ligature in most names, e.g. "الأغذية"
    assert "شهادة السجل التجاري" in cr
    assert "(محاكاة)" in docs.texts["credit_report"]  # brackets the right way round


def test_no_unmapped_glyphs(rendered):
    _, docs = rendered
    assert not any("(cid:" in t for t in docs.texts.values())


def test_missing_documents_are_reported_not_guessed(tmp_path):
    src = DEMO / "demo-bakery-supplier" / "documents" / "clean"
    for f in src.glob("*.pdf"):
        if f.stem not in ("credit_report", "income_statement"):
            shutil.copy(f, tmp_path / f.name)
    docs = load_documents(tmp_path)
    # credit report is required, so it is a gap; no income statement is a fact about the business
    assert docs.missing == ["credit_report"]
    assert not docs.has("income_statement")
    assert len(docs.texts) == len(REQUIRED_DOCS) - 1


def test_reading_is_deterministic():
    path = DEMO / "demo-bakery-supplier" / "documents" / "clean" / "bank_statement.pdf"
    assert read_pdf(path) == read_pdf(path)
