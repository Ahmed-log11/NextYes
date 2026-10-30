"""Extraction pipeline: reader -> assemble -> evaluate, tested without an API key.

The oracle reader returns what the documents say. With it, our own code must rebuild
the true snapshot exactly at every level, request exactly the missing documents and
find exactly the planted conflicts. Planted reading mistakes must be caught.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engine import FinancialSnapshot
from app.extract.assemble import assemble, extract, read_all
from app.extract.evaluate import score_business
from app.extract.llm import AnthropicReader, CachedReader, CallLog, CallRecord, DocInput, Reading, ReadError
from app.extract.oracle import OracleReader
from app.extract.pdf_text import OPTIONAL_DOCS, REQUIRED_DOCS, DocumentSet
from app.extract.schemas import TOOLS, instructions
from app.synth.dataset import build
from app.synth.variants import LEVELS, plan_noise

ALL = [b for split in build().values() for b in split]
DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"


def _docset(b, level) -> DocumentSet:
    """What load_documents would return, without rendering PDFs (the oracle ignores text)."""
    plan = plan_noise(b, level)
    names = list(REQUIRED_DOCS) + (list(OPTIONAL_DOCS) if b.snapshot.financial_statements_available else [])
    ds = DocumentSet()
    for n in names:
        if n in plan.missing:
            ds.missing.append(n)
        elif n in plan.scanned:
            ds.scanned[n] = Path(f"{n}.pdf")
        else:
            ds.texts[n] = ""
    return ds


def _run(b, level, mistakes=frozenset()):
    reader = OracleReader(b, level, mistakes)
    docs, log = _docset(b, level), CallLog()
    readings, unreadable = read_all(docs, reader, log)
    return assemble(b.meta.business_id, docs, readings, unreadable, log)


def _noise(b, level):
    return plan_noise(b, level).model_dump()


# --- the pipeline ceiling: perfect reading -> perfect result -----------------


@pytest.mark.parametrize("level", LEVELS)
def test_perfect_reading_rebuilds_the_true_snapshot(level):
    for b in ALL:
        r = _run(b, level)
        plan = plan_noise(b, level)
        assert r.missing_documents == plan.missing
        if plan.missing:
            assert r.snapshot is None and r.unresolved_fields  # never guesses
        else:
            assert r.snapshot == b.snapshot, b.meta.business_id
        assert sorted(c.code for c in r.conflicts) == sorted(c.code for c in plan.conflicts)
        assert all(c.passed for c in r.checks), [c for c in r.checks if not c.passed]


@pytest.mark.parametrize("level", LEVELS)
def test_perfect_reading_scores_perfectly(level):
    for b in ALL:
        row = score_business(_run(b, level), b.snapshot, _noise(b, level))
        assert all(v is not False for v in row["fields"].values()), row["fields"]
        assert all(v is not False for v in row["verdict"].values())
        assert row["missing_exact"] and row["conflicts_found"] == row["conflicts_true"]


def test_conflicts_use_the_authoritative_document():
    b = next(b for b in ALL if {c.code for c in plan_noise(b, "hard").conflicts} == {"APP_OPERATING_SINCE",
                                                                                    "INCOME_REVENUE_INFLATED"}
             and not plan_noise(b, "hard").missing)
    r = _run(b, "hard")
    assert r.snapshot.operating_months == b.snapshot.operating_months  # CR, not the application
    assert r.snapshot.monthly_revenue_sar == b.snapshot.monthly_revenue_sar  # bank, not the income statement


# --- the evaluation catches real reading mistakes ----------------------------


def _first(pred):
    return next(b for b in ALL if pred(b) and not plan_noise(b, "realistic").missing)


def test_owner_money_counted_as_revenue_is_caught():
    from app.synth.ledger import build_ledger
    b = _first(lambda b: any(t.category == "owner" for t in build_ledger(b).statement))
    row = score_business(_run(b, "realistic", frozenset({"owner_as_revenue"})), b.snapshot, _noise(b, "realistic"))
    assert row["fields"]["monthly_revenue_sar"] is False


def test_personal_spending_counted_as_costs_is_caught():
    b = _first(lambda b: not b.snapshot.separate_business_account)
    row = score_business(_run(b, "realistic", frozenset({"personal_as_opex"})), b.snapshot, _noise(b, "realistic"))
    assert row["fields"]["operating_margin"] is False


@pytest.mark.parametrize("mistake", ["drop_last_line", "debit_credit_swap_first_line"])
def test_misread_statement_fails_the_balance_check(mistake):
    r = _run(ALL[0], "clean", frozenset({mistake}))
    assert not next(c for c in r.checks if c.name == "BALANCE_RECONCILES").passed


def test_unreadable_document_blocks_the_snapshot():
    class Failing(OracleReader):
        def read(self, doc, context):
            if doc.name == "credit_report":
                raise ReadError("cut off")
            return super().read(doc, context)

    b = ALL[0]
    docs, log = _docset(b, "clean"), CallLog()
    readings, unreadable = read_all(docs, Failing(b, "clean"), log)
    r = assemble(b.meta.business_id, docs, readings, unreadable, log)
    assert r.unreadable_documents == ["credit_report"] and r.snapshot is None


# --- the real documents on disk (demo is committed) --------------------------


@pytest.mark.parametrize("level", LEVELS)
def test_demo_end_to_end_from_pdfs(level):
    folder = DEMO / "demo-bakery-supplier" / "documents" / level
    r = extract(folder, OracleReader.for_folder(folder))
    truth = FinancialSnapshot.model_validate(
        json.loads((DEMO / "demo-bakery-supplier" / "business.json").read_text(encoding="utf-8"))["snapshot"])
    noise = json.loads((folder / "noise.json").read_text(encoding="utf-8"))
    assert r.business_id == "demo-bakery-supplier"
    assert r.missing_documents == noise["missing"]
    if not noise["missing"]:
        assert r.snapshot == truth


# --- reader plumbing: prompts, cache, API call shape -------------------------


def test_bank_instructions_carry_the_owner_and_lenders():
    text = instructions("bank_statement", {"owner_name": "Omar Al-Ghamdi", "owner_name_ar": "عمر الغامدي",
                                           "lenders": "Sample Bank"})
    assert "Omar Al-Ghamdi" in text and "عمر الغامدي" in text and "Sample Bank" in text
    assert "owner's name is unknown" in instructions("bank_statement", {})


def test_every_document_has_a_tool():
    assert set(TOOLS) == set(REQUIRED_DOCS) | set(OPTIONAL_DOCS)


class Counting:
    model = "counting"

    def __init__(self):
        self.n = 0

    def read(self, doc, context):
        self.n += 1
        return Reading({"value": self.n}, CallRecord(doc.name, self.model, 10, 5, 1.0, False))


def test_cache_returns_the_same_answer_without_calling_again(tmp_path):
    inner = Counting()
    cached = CachedReader(inner, tmp_path)
    doc = DocInput("tax_compliance", text="some text")
    first, second = cached.read(doc, {}), cached.read(doc, {})
    assert inner.n == 1 and first.fields == second.fields and second.record.cached
    cached.read(DocInput("tax_compliance", text="other text"), {})
    assert inner.n == 2  # different document, different key


def _fake_api(stop_reason="tool_use"):
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason=stop_reason, usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                               content=[SimpleNamespace(type="tool_use", input={"revenue": 1.0})])

    reader = AnthropicReader.__new__(AnthropicReader)
    reader.model = "claude-haiku-5-5"
    reader.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return reader, calls


def test_api_call_forces_the_tool_and_sends_text():
    reader, calls = _fake_api()
    out = reader.read(DocInput("income_statement", text="Revenue 1"), {})
    kw = calls[0]
    assert kw["tool_choice"] == {"type": "tool", "name": "record_income_statement"}
    assert kw["messages"][0]["content"][0]["type"] == "text"
    assert out.fields == {"revenue": 1.0} and out.record.input_tokens == 100


def test_scanned_document_is_sent_as_images():
    reader, calls = _fake_api()
    scanned = DEMO / "demo-online-store" / "documents" / "hard" / "bank_statement.pdf"
    reader.read(DocInput("bank_statement", pdf_path=scanned), {})
    kinds = [c["type"] for c in calls[0]["messages"][0]["content"]]
    assert kinds.count("image") >= 1 and kinds[-1] == "text"


def test_cut_off_answer_is_an_error_not_a_partial_result():
    reader, _ = _fake_api(stop_reason="max_tokens")
    with pytest.raises(ReadError):
        reader.read(DocInput("income_statement", text="x"), {})
