from __future__ import annotations

import pytest

from app.engine import assess, load_policy
from app.synth.dataset import DEMO, DEV_CLEAN, DEV_SIZE, HELDOUT_CLEAN, HELDOUT_SIZE, build
from app.synth.generator import make_business
from app.synth.issues import ALL_CODES

BANK = load_policy("commercial_bank_sme")
BANK_CODES = {r.id for r in BANK.rules}


@pytest.fixture(scope="module")
def data():
    return build()


def test_sizes(data):
    assert len(data["dev"]) == DEV_SIZE
    assert len(data["heldout"]) == HELDOUT_SIZE
    assert len(data["demo"]) == len(DEMO)


def test_same_seed_same_business():
    a = make_business("x", 42, ["CR_EXPIRING", "DSCR_LOW"])
    b = make_business("x", 42, ["CR_EXPIRING", "DSCR_LOW"])
    assert a.model_dump() == b.model_dump()


def test_different_seed_different_business():
    a = make_business("x", 1, [])
    b = make_business("x", 2, [])
    assert a.snapshot.monthly_revenue_sar != b.snapshot.monthly_revenue_sar


def test_contradictory_issues_rejected():
    with pytest.raises(ValueError):
        make_business("x", 1, ["CR_INVALID", "CR_EXPIRING"])


def test_unknown_issue_rejected():
    with pytest.raises(ValueError):
        make_business("x", 1, ["NOT_A_REAL_ISSUE"])


@pytest.mark.parametrize("code", ALL_CODES)
def test_each_issue_is_detected_alone(code):
    """Plant one issue in a healthy business → the bank reports exactly that issue."""
    b = make_business("x", 123, [code])
    expected = {code} & BANK_CODES  # REVENUE_LOW is a digital-lender rule only
    assert set(assess(b.snapshot, BANK).blocker_codes) == expected


def test_every_business_matches_its_planted_issues(data):
    """Ground-truth integrity across all 63 businesses: no missing and no extra bank blockers."""
    for split in ("dev", "heldout", "demo"):
        for b in data[split]:
            got = set(assess(b.snapshot, BANK).blocker_codes)
            want = set(b.meta.planted_issues) & BANK_CODES
            assert got == want, f"{b.meta.business_id}: planted {want}, engine found {got}"


def test_clean_businesses_are_ready_for_both_lenders(data):
    clean = [b for s in ("dev", "heldout") for b in data[s] if not b.meta.planted_issues]
    assert len(clean) == DEV_CLEAN + HELDOUT_CLEAN
    for b in clean:
        assert all(t.ready for t in b.truth().values()), b.meta.business_id


def test_heldout_combinations_never_seen_in_dev(data):
    dev = {frozenset(b.meta.planted_issues) for b in data["dev"] if b.meta.planted_issues}
    held = [frozenset(b.meta.planted_issues) for b in data["heldout"] if b.meta.planted_issues]
    assert held and not (set(held) & dev)


def test_heldout_seeds_differ_from_dev(data):
    assert not ({b.meta.seed for b in data["dev"]} & {b.meta.seed for b in data["heldout"]})


def test_every_issue_appears_in_dev(data):
    seen = {c for b in data["dev"] for c in b.meta.planted_issues}
    assert seen == set(ALL_CODES)
