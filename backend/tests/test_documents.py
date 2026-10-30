"""The documents must agree with the true snapshot.

If these hold, a perfect reader of the PDFs rebuilds the snapshot exactly,
so any gap the evaluation finds later is the agent's, not the data's.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from app.synth.dataset import build
from app.synth.documents import render_all
from app.synth.ledger import build_ledger

ALL = [b for split in build().values() for b in split]


@pytest.fixture(scope="module", params=ALL, ids=lambda b: b.meta.business_id)
def pair(request):
    return request.param, build_ledger(request.param)


def test_monthly_revenue_matches(pair):
    b, L = pair
    by_month = defaultdict(int)
    for t in L.statement:
        if t.category == "revenue":
            by_month[(t.day.year, t.day.month)] += t.credit
    got = [by_month[(m.year, m.month)] / 100 for m in L.month_starts]
    assert got == pytest.approx(b.snapshot.monthly_revenue_sar, abs=0.01)


def test_operating_margin_matches(pair):
    b, L = pair
    rev = sum(t.credit for t in L.statement if t.category == "revenue")
    opex = sum(t.debit for t in L.statement if t.category == "opex")
    assert 1 - opex / rev == pytest.approx(b.snapshot.operating_margin, abs=1e-4)


def test_debt_and_defaults_match(pair):
    b, L = pair
    regular = sum(f.instalment for f in L.facilities if f.status == "regular")
    assert regular / 100 == pytest.approx(b.snapshot.existing_monthly_debt_service_sar, abs=0.01)
    assert any(f.status == "default" for f in L.facilities) == b.snapshot.has_active_defaults
    monthly_debits = sum(t.debit for t in L.statement if t.category == "debt") / 12 / 100
    assert monthly_debits == pytest.approx(b.snapshot.existing_monthly_debt_service_sar, abs=0.01)


def test_receivables_match(pair):
    b, L = pair
    total = sum(a + b31 + c + o for _, _, a, b31, c, o in L.aging) / 100
    over = sum(o for *_, o in L.aging) / 100
    assert total == pytest.approx(b.snapshot.receivables_outstanding_sar, abs=0.01)
    assert over == pytest.approx(b.snapshot.receivables_overdue_90d_sar, abs=0.01)


def test_vat_lateness_matches(pair):
    b, L = pair
    late = any(filed > due for _, due, filed in L.vat_returns)
    assert late == (not b.snapshot.vat_filed_on_time)


def test_account_and_history_match(pair):
    b, L = pair
    s = b.snapshot
    assert (L.account_type == "personal") == (not s.separate_business_account)
    has_personal = any(t.category == "personal" for t in L.statement)
    assert has_personal == (not s.separate_business_account)
    months = round((s.as_of - L.cr_issue_date).days / 30.44)
    assert months == s.operating_months


def test_pdfs_render(tmp_path):
    """Render two businesses end to end: one with statements, one without."""
    with_fs = next(b for b in ALL if b.snapshot.financial_statements_available)
    without = next(b for b in ALL if not b.snapshot.financial_statements_available)
    assert "income_statement.pdf" in render_all(with_fs, tmp_path / "a")
    files = render_all(without, tmp_path / "b")
    assert "income_statement.pdf" not in files and len(files) == 6
    assert all((tmp_path / "b" / f).stat().st_size > 5_000 for f in files)
