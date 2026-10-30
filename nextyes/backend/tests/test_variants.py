"""Document difficulty levels: messier presentation, same truth.

What must hold for the evaluation to mean anything:
- the numbers a perfect reader would recover are identical at every level;
- held-out wording never appears in dev;
- everything injected (missing, scanned, conflicts) is recorded and actually present.
"""

from __future__ import annotations

import json
import re

import pytest

from app.extract.pdf_text import REQUIRED_DOCS, load_documents
from app.synth.dataset import build
from app.synth.documents import render_all
from app.synth.ledger import build_ledger
from app.synth.variants import LEVELS, WORDING, plan_noise, reword

ALL = [b for split in build().values() for b in split]
AMOUNT = r"-?\d{1,3}(?:,\d{3})*\.\d{2}"


def _money(x: str) -> int:
    return round(float(x.replace(",", "")) * 100)


# --- plans and wording (fast, every business) --------------------------------


def test_heldout_wording_never_appears_in_dev():
    for kind in WORDING["dev"]:
        dev = {t for pair in WORDING["dev"][kind] for t in pair}
        held = {t for pair in WORDING["heldout"][kind] for t in pair}
        assert held, kind
        assert not dev & held, f"{kind}: shared wording {dev & held}"


@pytest.mark.parametrize("level", LEVELS)
def test_plans_are_deterministic_and_consistent(level):
    for b in ALL:
        plan = plan_noise(b, level)
        assert plan == plan_noise(b, level)
        assert set(plan.missing) <= set(REQUIRED_DOCS) and "bank_statement" not in plan.missing
        assert not set(plan.missing) & set(plan.scanned)
        for c in plan.conflicts:  # a conflict is only detectable if its authority is there
            assert c.authoritative_document not in plan.missing
        expected_pool = "heldout" if b.meta.business_id.startswith("heldout") else "dev"
        assert plan.wording_pool == expected_pool
        if level == "clean":
            assert not (plan.missing or plan.scanned or plan.conflicts)


def test_owner_is_the_same_at_every_level():
    for b in ALL:
        owners = {(plan_noise(b, lv).owner_en) for lv in LEVELS}
        assert len(owners) == 1


@pytest.mark.parametrize("level", ["realistic", "hard"])
def test_rewording_changes_text_never_money(level):
    for b in ALL:
        L, plan = build_ledger(b), plan_noise(b, level)
        lines = reword(L, plan)
        assert [t for t, _, _ in lines] == L.statement  # same transactions, same order
        for t, en, ar in lines:
            assert ar  # Arabic is always there; English may be dropped
            if t.kind == "owner_injection":
                assert plan.owner_ar in ar  # the owner's own money, named only by the owner's name


def test_clean_level_is_the_original_wording():
    b = ALL[0]
    L = build_ledger(b)
    assert [(en, ar) for _, en, ar in reword(L, plan_noise(b, "clean"))] == [(t.desc_en, t.desc_ar) for t in L.statement]


def test_levels_cover_every_bank_format_and_some_traps():
    plans = [plan_noise(b, "hard") for b in ALL] + [plan_noise(b, "realistic") for b in ALL]
    assert {p.bank_format for p in plans} == {"classic", "signed", "arabic_first"}
    assert sum(bool(p.missing) for p in plans) >= 10
    hard = [plan_noise(b, "hard") for b in ALL]
    assert all(p.scanned and p.conflicts for p in hard)


# --- rendered documents (slower, one business per bank format) ---------------


def _one_per_format():
    picked = {}
    for b in ALL:
        fmt = plan_noise(b, "realistic").bank_format
        picked.setdefault(fmt, b)
    return list(picked.values())


@pytest.fixture(scope="module", params=_one_per_format(), ids=lambda b: plan_noise(b, "realistic").bank_format)
def realistic(request, tmp_path_factory):
    b = request.param
    folder = tmp_path_factory.mktemp(b.meta.business_id)
    render_all(b, folder, "realistic")
    return b, folder, load_documents(folder)


def test_every_statement_amount_is_recoverable_with_its_direction(realistic):
    """For each bank layout, a reader of the text gets every movement and whether
    money came in or went out — so the true snapshot is still recoverable."""
    b, _, docs = realistic
    L, plan = build_ledger(b), plan_noise(b, "realistic")
    lines = docs.texts["bank_statement"].splitlines()
    date_re = r"\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\s" if plan.bank_format != "arabic_first" else r".*\d{2}-\d{2}-\d{4}\s*$"
    rows = [l for l in lines if re.match(date_re, l)]
    assert len(rows) == len(L.statement)

    if plan.bank_format == "signed":
        for line, t in zip(rows, L.statement):
            amount = re.findall(AMOUNT, line)[-2]  # movement, then balance
            assert _money(amount) == (t.credit or -t.debit), line
        return

    header = next(l for l in lines if "مدين" in l and "دائن" in l and "الرصيد" in l)
    if plan.bank_format == "classic":
        cols = {"debit": header.index("Debit") + len("Debit / مدين"),
                "credit": header.index("Credit") + len("Credit / دائن")}
        pick = 0  # movement comes first, balance last
    else:  # arabic_first: balance | credit | debit | ...
        cols = {"debit": header.index("مدين") + len("مدين"), "credit": header.index("دائن") + len("دائن")}
        pick = 1
    for line, t in zip(rows, L.statement):
        m = list(re.finditer(AMOUNT, line))
        assert len(m) == 2, line
        mv = m[pick]
        side = min(cols, key=lambda k: abs(cols[k] - mv.end()))
        assert side == ("debit" if t.debit else "credit"), line
        assert _money(mv.group()) == (t.debit or t.credit)


def test_owner_is_on_the_cr_certificate(realistic):
    b, _, docs = realistic
    if "cr_certificate" in docs.texts:
        assert plan_noise(b, "realistic").owner_ar in docs.texts["cr_certificate"]


def test_noise_file_matches_what_was_written(realistic):
    b, folder, docs = realistic
    noise = json.loads((folder / "noise.json").read_text(encoding="utf-8"))
    assert noise == plan_noise(b, "realistic").model_dump()
    assert docs.missing == noise["missing"]


def test_hard_level_scans_and_conflicts(tmp_path):
    b = next(b for b in ALL if any(c.code == "INCOME_REVENUE_INFLATED" for c in plan_noise(b, "hard").conflicts))
    plan = plan_noise(b, "hard")
    render_all(b, tmp_path, "hard")
    docs = load_documents(tmp_path)
    assert sorted(docs.scanned) == plan.scanned  # image only: no text to read
    for c in plan.conflicts:
        if c.document in docs.texts:
            shown = f"{float(c.shown):,.2f}" if c.field == "revenue_sar" else c.shown
            assert shown in docs.texts[c.document], c.code
