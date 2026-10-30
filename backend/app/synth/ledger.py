"""Turn a business's true snapshot into the detailed content of its documents.

The documents must be CONSISTENT with the snapshot, so that a perfect reader
of the PDFs would rebuild the snapshot exactly:

  monthly revenue    = sum of customer receipts in the bank statement that month
  operating margin   = 1 - operating expenses / revenue (bank statement, whole year)
  existing debt      = sum of instalments of facilities in good standing (credit report)
  receivables        = aging report totals (90+ bucket = overdue)
  ...

Money is handled in halalas (integer) and rendered with 2 decimals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .generator import SyntheticBusiness

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CUSTOMERS = [
    ("Al-Safwa Restaurants", "مطاعم الصفوة"), ("Bayt Al-Khair Markets", "أسواق بيت الخير"),
    ("Nujoom Catering", "نجوم للإعاشة"), ("Al-Riyada Hotels", "فنادق الريادة"),
    ("Masarat Trading", "مسارات للتجارة"), ("Al-Ufuq Schools", "مدارس الأفق"),
    ("Qasr Al-Diyafa", "قصر الضيافة"), ("Areej Cafes", "مقاهي أريج"),
    ("Al-Mawared Co.", "شركة الموارد"), ("Sahl Express", "سهل إكسبرس"),
]


@dataclass
class Txn:
    day: date
    desc_en: str
    desc_ar: str
    debit: int = 0  # halalas
    credit: int = 0
    category: str = ""  # ground truth only; NOT printed on the PDF
    balance: int = 0
    kind: str = ""  # finer than category (e.g. "payroll"); lets variants reword the line
    party_en: str = ""  # counterparty, when there is one
    party_ar: str = ""


@dataclass
class Facility:
    lender_en: str
    lender_ar: str
    kind_en: str
    kind_ar: str
    instalment: int  # halalas / month
    outstanding: int
    status: str  # "regular" | "default"


@dataclass
class Ledger:
    business: SyntheticBusiness
    month_starts: list[date]
    statement: list[Txn]
    opening_balance: int
    account_type: str  # "business" | "personal"
    facilities: list[Facility]
    aging: list[tuple[str, str, int, int, int, int]]  # customer en, ar, 0-30, 31-60, 61-90, 90+
    vat_returns: list[tuple[str, date, date]]  # period, due, filed
    cr_number: str
    cr_issue_date: date
    extras: dict = field(default_factory=dict)


def _h(sar: float) -> int:
    return round(sar * 100)


def _split(total: int, parts: int, rng: random.Random, spread: float = 0.6) -> list[int]:
    """Split `total` halalas into `parts` positive pieces that sum exactly."""
    weights = [rng.uniform(1 - spread, 1 + spread) for _ in range(parts)]
    s = sum(weights)
    pieces = [int(total * w / s) for w in weights]
    pieces[-1] += total - sum(pieces)
    return pieces


def _month_starts(as_of: date) -> list[date]:
    out, y, m = [], as_of.year, as_of.month
    for _ in range(12):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _days(start: date, n: int, rng: random.Random) -> list[date]:
    nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    span = (nxt - start).days
    return sorted(start + timedelta(days=rng.randrange(span)) for _ in range(n))


def build_ledger(b: SyntheticBusiness) -> Ledger:
    s, rng = b.snapshot, random.Random(b.meta.seed * 7919)
    months = _month_starts(s.as_of)

    # --- credit facilities: regular ones carry the existing monthly debt service ---
    facilities: list[Facility] = []
    debt = _h(s.existing_monthly_debt_service_sar)
    if debt:
        n = rng.choice([1, 2])
        lenders = [("Sample Bank (simulated)", "البنك التجريبي"), ("Demo Finance Co. (simulated)", "شركة التمويل التجريبية")]
        kinds = [("Vehicle financing", "تمويل مركبات"), ("Working capital", "رأس مال عامل")]
        for i, inst in enumerate(_split(debt, n, rng, 0.3)):
            facilities.append(Facility(*lenders[i], *kinds[i], inst, inst * rng.randint(10, 40), "regular"))
    if s.has_active_defaults:
        facilities.append(Facility("Demo Trade Supplier (simulated)", "مورد تجاري تجريبي",
                                   "Trade credit", "ائتمان تجاري", 0, _h(rng.uniform(15_000, 90_000)), "default"))

    # --- bank statement ---
    personal = not s.separate_business_account
    custs = rng.sample(CUSTOMERS, 6)
    injection_month = rng.randrange(12) if rng.random() < 0.3 else None
    txns: list[Txn] = []
    for mi, (start, rev_sar) in enumerate(zip(months, s.monthly_revenue_sar)):
        rev = _h(rev_sar)
        k = rng.randint(4, 6)
        for day, amt in zip(_days(start, k, rng), _split(rev, k, rng)):
            if rng.random() < 0.35:
                txns.append(Txn(day, "POS settlement", "تسوية نقاط البيع", credit=amt, category="revenue", kind="pos"))
            else:
                en, ar = rng.choice(custs)
                txns.append(Txn(day, f"Incoming transfer - {en}", f"حوالة واردة - {ar}", credit=amt,
                                category="revenue", kind="transfer_in", party_en=en, party_ar=ar))

        opex = round(rev * (1 - s.operating_margin))
        salaries, rent, suppliers, utilities = _split(opex, 4, rng, 0.25)
        d = _days(start, 4, rng)
        txns += [
            Txn(d[0], "Payroll - employee salaries", "رواتب الموظفين", debit=salaries, category="opex", kind="payroll"),
            Txn(d[1], "Rent payment - business premises", "إيجار مقر المنشأة", debit=rent, category="opex", kind="rent"),
            Txn(d[2], "Supplier payments", "مدفوعات الموردين", debit=suppliers, category="opex", kind="suppliers"),
            Txn(d[3], "Utilities and telecom", "كهرباء واتصالات", debit=utilities, category="opex", kind="utilities"),
        ]
        for f in facilities:
            if f.status == "regular":
                txns.append(Txn(start + timedelta(days=24), f"Financing instalment - {f.lender_en}",
                                f"قسط تمويل - {f.lender_ar}", debit=f.instalment, category="debt",
                                kind="instalment", party_en=f.lender_en, party_ar=f.lender_ar))
        if personal:
            for day in _days(start, rng.randint(2, 3), rng):
                en, ar, kind = rng.choice([("School fees", "رسوم مدرسية", "school"),
                                           ("Personal card payment", "سداد بطاقة شخصية", "card"),
                                           ("Family transfer", "تحويل عائلي", "family"),
                                           ("Home rent", "إيجار سكن", "home_rent")])
                txns.append(Txn(day, en, ar, debit=_h(rng.uniform(1_500, 7_000)), category="personal", kind=kind))
        if mi == injection_month:
            txns.append(Txn(start + timedelta(days=3), "Owner capital injection", "ضخ رأس مال من المالك",
                            credit=_h(rng.uniform(20_000, 80_000)), category="owner", kind="owner_injection"))

    txns.sort(key=lambda t: (t.day, -t.credit))
    opening = _h(rng.uniform(40_000, 250_000))
    bal = opening
    for t in txns:
        bal += t.credit - t.debit
        t.balance = bal

    # --- receivables aging: 90+ bucket is exactly the overdue amount ---
    total, over = _h(s.receivables_outstanding_sar), _h(s.receivables_overdue_90d_sar)
    rest = total - over
    n = rng.randint(4, 6)
    names = rng.sample(CUSTOMERS, n)
    cur, b31, b61 = (_split(x, n, rng) for x in _split(rest, 3, rng, 0.3)) if rest else ([0] * n,) * 3
    o90 = _split(over, n, rng, 0.9) if over else [0] * n
    aging = [(en, ar, cur[i], b31[i], b61[i], o90[i]) for i, (en, ar) in enumerate(names)]

    # --- VAT returns: last 4 quarters; late filing when vat_filed_on_time is False ---
    # Quarterly returns are due by the end of the month after the quarter.
    # The last four quarters whose deadline has passed by the as-of date.
    quarters = [
        ("Q2 2026", date(2026, 7, 31)), ("Q1 2026", date(2026, 4, 30)),
        ("Q4 2025", date(2026, 1, 31)), ("Q3 2025", date(2025, 10, 31)),
    ]
    late_idx = set(rng.sample(range(4), rng.randint(1, 2))) if not s.vat_filed_on_time else set()
    vat = []
    for i, (period, due) in enumerate(quarters):
        if i in late_idx:
            filed = due + timedelta(days=rng.randint(5, 40))
        else:
            filed = due - timedelta(days=rng.randint(1, 20))
        vat.append((period, due, filed))

    issue = s.as_of - timedelta(days=round(s.operating_months * 30.44))
    return Ledger(
        business=b, month_starts=months, statement=txns, opening_balance=opening,
        account_type="personal" if personal else "business", facilities=facilities, aging=aging,
        vat_returns=vat, cr_number=f"10{rng.randint(10_000_000, 99_999_999)}", cr_issue_date=issue,
    )
