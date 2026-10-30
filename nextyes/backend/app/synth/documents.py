"""Render a business's documents as bilingual (English / Arabic) PDFs.

    python -m app.synth.documents                          # all splits, all levels
    python -m app.synth.documents --split demo --level hard

Output: data/<split>/<business>/documents/<level>/*.pdf + noise.json.
Levels (clean / realistic / hard) are defined in variants.py.

Every document is clearly marked SIMULATED and uses invented issuers, so it
can never be mistaken for a real record. Each business gets:

  bank_statement.pdf        12 months of transactions (no category labels)
  cr_certificate.pdf        commercial registration: issue, expiry, status
  credit_report.pdf         existing facilities and their status
  receivables_aging.pdf     customer balances by age bucket
  tax_compliance.pdf        e-invoicing integration and VAT filing history
  financing_application.pdf requested amount, tenor, security, attachments
  income_statement.pdf      only when financial statements are available
"""

from __future__ import annotations

import argparse
import io
import json
import random
from datetime import date
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageFilter

from .dataset import DATA_DIR
from .generator import SyntheticBusiness
from .ledger import Ledger, build_ledger
from .variants import LEVELS, Level, NoisePlan, conflict_value, plan_noise, reword

FONT_DIR = Path(__file__).parent / "fonts"
INK, MUTED, RULE, BAND = (20, 32, 27), (90, 105, 99), (210, 216, 212), (240, 243, 241)
MIN_FONT = 5.5  # smallest size a table cell may shrink to before we call it a layout bug


def money(halalas: int) -> str:
    return f"{halalas / 100:,.2f}"


def d(x: date) -> str:
    return x.isoformat()


class Doc(FPDF):
    def __init__(self, title_en: str, title_ar: str, issuer_en: str, issuer_ar: str):
        super().__init__(format="A4")
        self.add_font("dv", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("dv", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.set_text_shaping(True)
        self.set_auto_page_break(True, margin=18)
        self.title_en, self.title_ar = title_en, title_ar
        self.issuer_en, self.issuer_ar = issuer_en, issuer_ar
        self.add_page()

    def header(self) -> None:
        self.set_font("dv", "B", 13)
        self.set_text_color(*INK)
        self.cell(95, 8, self.title_en)
        self.cell(0, 8, self.title_ar, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("dv", "", 8.5)
        self.set_text_color(*MUTED)
        self.cell(95, 5, self.issuer_en)
        self.cell(0, 5, self.issuer_ar, align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
        self.ln(5)
        self.set_text_color(*INK)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("dv", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"SIMULATED DOCUMENT FOR A HACKATHON DEMO - NOT A REAL RECORD  ·  مستند محاكاة  ·  page {self.page_no()}",
                  align="C")

    def kv(self, rows: list[tuple[str, str, str]]) -> None:
        """Rows of (label EN, label AR, value)."""
        self.set_font("dv", "", 9.5)
        for en, ar, val in rows:
            self.set_text_color(*MUTED)
            self.cell(60, 7, en)
            self.set_text_color(*INK)
            self.cell(70, 7, val)
            self.set_text_color(*MUTED)
            self.cell(0, 7, ar, align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def section(self, en: str, ar: str) -> None:
        self.ln(2)
        self.set_font("dv", "B", 10.5)
        self.set_text_color(*INK)
        self.cell(95, 7, en)
        self.cell(0, 7, ar, align="R", new_x="LMARGIN", new_y="NEXT")

    def fitted_cell(self, w: float, h: float, text: str, style: str, align: str, fill: bool = False) -> None:
        """A cell whose text is shrunk until it fits, so it never runs into the next column
        (overlapping text would make the document unreadable, for a person or a model)."""
        size = 8.0
        self.set_font("dv", style, size)
        while self.get_string_width(text) > w - 2 * self.c_margin and size > MIN_FONT:
            size -= 0.25
            self.set_font("dv", style, size)
        if self.get_string_width(text) > w - 2 * self.c_margin:
            raise ValueError(f"text does not fit a {w} mm column even at {MIN_FONT} pt: {text!r}")
        self.cell(w, h, text, fill=fill, align=align)

    def grid(self, head: list[str], rows: list[list[str]], widths: list[int], align: str = "LRRRRR") -> None:
        self.set_fill_color(*BAND)
        for h, w, a in zip(head, widths, align):
            self.fitted_cell(w, 7, h, "B", "L" if a == "L" else "R", fill=True)
        self.ln()
        for r in rows:
            for v, w, a in zip(r, widths, align):
                self.fitted_cell(w, 6, v, "", "L" if a == "L" else "R")
            self.ln()
        self.ln(2)


def _who(L: Ledger) -> list[tuple[str, str, str]]:
    m = L.business.meta
    return [
        ("Business name", "اسم المنشأة", m.name_en),
        ("Arabic name", "الاسم التجاري", m.name_ar),
        ("Commercial registration", "رقم السجل التجاري", L.cr_number),
        ("City", "المدينة", f"{m.city_en} / {m.city_ar}"),
    ]


BANKS = {
    "classic": ("Sample Bank (simulated)", "البنك التجريبي (محاكاة)"),
    "signed": ("Coastal Bank (simulated)", "بنك الساحل (محاكاة)"),
    "arabic_first": ("Al-Waha Bank (simulated)", "مصرف الواحة (محاكاة)"),
}


def bank_statement(L: Ledger, plan: NoisePlan) -> Doc:
    s = L.business.snapshot
    p = Doc("Statement of Account", "كشف حساب", *BANKS[plan.bank_format])
    acct_en = "Personal current account" if L.account_type == "personal" else "Business current account"
    acct_ar = "حساب جاري شخصي" if L.account_type == "personal" else "حساب جاري تجاري"
    p.kv(_who(L) + [
        ("Account type", "نوع الحساب", f"{acct_en} / {acct_ar}"),
        ("Period", "الفترة", f"{d(L.month_starts[0])} to {d(s.as_of)}"),
        ("Opening balance (SAR)", "الرصيد الافتتاحي", money(L.opening_balance)),
    ])
    lines = reword(L, plan)

    def text(en: str, ar: str) -> str:
        return f"{en} / {ar}" if en else ar

    if plan.bank_format == "classic":
        rows = [[d(t.day), text(en, ar), money(t.debit) if t.debit else "",
                 money(t.credit) if t.credit else "", money(t.balance)] for t, en, ar in lines]
        p.grid(["Date / التاريخ", "Description / البيان", "Debit / مدين", "Credit / دائن", "Balance / الرصيد"],
               rows, [20, 102, 22, 22, 24], "LLRRR")
    elif plan.bank_format == "signed":
        # one signed amount column, day-first dates, a reference number per line
        ref = random.Random(f"{L.business.meta.seed}-ref")
        rows = [[t.day.strftime("%d/%m/%Y"), f"FT{ref.randint(10**7, 10**8 - 1)}", text(en, ar),
                 money(t.credit) if t.credit else "-" + money(t.debit), money(t.balance)] for t, en, ar in lines]
        p.grid(["Date", "Reference", "Details / التفاصيل", "Amount (SAR)", "Balance"],
               rows, [20, 24, 92, 26, 28], "LLLRR")
    else:
        # laid out right to left: date on the right, balance on the left, Arabic headers only
        rows = [[money(t.balance), money(t.credit) if t.credit else "", money(t.debit) if t.debit else "",
                 text(en, ar), t.day.strftime("%d-%m-%Y")] for t, en, ar in lines]
        p.grid(["الرصيد", "دائن", "مدين", "البيان", "التاريخ"], rows, [24, 22, 22, 98, 24], "RRRRR")
    p.kv([("Closing balance (SAR)", "الرصيد الختامي", money(L.statement[-1].balance))])
    return p


def cr_certificate(L: Ledger, plan: NoisePlan) -> Doc:
    s = L.business.snapshot
    status = ("Active", "نشط") if s.cr_active else ("Suspended", "موقوف")
    p = Doc("Commercial Registration Certificate", "شهادة السجل التجاري",
            "Commercial registry (simulated)", "السجل التجاري (محاكاة)")
    p.kv(_who(L) + [
        ("Activity", "النشاط", f"{L.business.meta.sector_en} / {L.business.meta.sector_ar}"),
        ("Owner", "المالك", f"{plan.owner_en} / {plan.owner_ar}"),
        ("Issue date", "تاريخ الإصدار", d(L.cr_issue_date)),
        ("Expiry date", "تاريخ الانتهاء", d(s.cr_expiry)),
        ("Status", "الحالة", f"{status[0]} / {status[1]}"),
    ])
    return p


def credit_report(L: Ledger) -> Doc:
    s = L.business.snapshot
    p = Doc("Commercial Credit Report", "تقرير ائتماني تجاري",
            "Credit bureau (simulated)", "مكتب المعلومات الائتمانية (محاكاة)")
    p.kv(_who(L) + [("Report date", "تاريخ التقرير", d(s.as_of))])
    p.section("Credit facilities", "التسهيلات الائتمانية")
    if not L.facilities:
        p.kv([("No facilities on record", "لا توجد تسهيلات مسجلة", "-")])
    else:
        rows = []
        for f in L.facilities:
            st = "Regular / منتظم" if f.status == "regular" else "Default, 90+ days past due / متعثر"
            rows.append([f"{f.lender_en} / {f.lender_ar}", f"{f.kind_en} / {f.kind_ar}",
                         money(f.instalment) if f.instalment else "-", money(f.outstanding), st])
        p.grid(["Lender / الجهة", "Type / النوع", "Monthly / القسط", "Outstanding / المتبقي", "Status / الحالة"],
               rows, [58, 40, 22, 30, 40], "LLRRL")
    return p


def receivables_aging(L: Ledger) -> Doc:
    s = L.business.snapshot
    p = Doc("Accounts Receivable Aging", "أعمار الذمم المدينة",
            "Prepared from the business's accounting system", "مستخرج من النظام المحاسبي للمنشأة")
    p.kv(_who(L)[:1] + [("As of", "بتاريخ", d(s.as_of))])
    rows = [[f"{en} / {ar}", money(a), money(b), money(c), money(o), money(a + b + c + o)]
            for en, ar, a, b, c, o in L.aging]
    tot = [sum(r[i] for r in L.aging) for i in range(2, 6)]
    rows.append(["Total / الإجمالي", *(money(x) for x in tot), money(sum(tot))])
    p.grid(["Customer / العميل", "0-30", "31-60", "61-90", "90+", "Total / الإجمالي"],
           rows, [66, 24, 24, 24, 24, 28])
    return p


def tax_compliance(L: Ledger) -> Doc:
    s = L.business.snapshot
    p = Doc("Tax Compliance Summary", "ملخص الامتثال الضريبي",
            "Tax authority portal extract (simulated)", "مستخرج من بوابة الجهة الضريبية (محاكاة)")
    einv = ("Integrated (Phase 2)", "مرتبط (المرحلة الثانية)") if s.einvoicing_compliant \
        else ("Not integrated", "غير مرتبط")
    p.kv(_who(L)[:3] + [("E-invoicing integration", "الربط بالفوترة الإلكترونية", f"{einv[0]} / {einv[1]}")])
    p.section("VAT returns", "إقرارات ضريبة القيمة المضافة")
    p.grid(["Period / الفترة", "Due date / تاريخ الاستحقاق", "Filed on / تاريخ التقديم"],
           [[per, d(due), d(filed)] for per, due, filed in L.vat_returns], [50, 60, 60], "LRR")
    return p


def financing_application(L: Ledger, plan: NoisePlan) -> Doc:
    s, m = L.business.snapshot, L.business.meta
    r = s.request
    p = Doc("SME Financing Application", "طلب تمويل منشأة", "Submitted by the business", "مقدم من المنشأة")
    collateral = ("Commercial property lien offered", "رهن عقار تجاري") if s.collateral_available else ("None", "لا يوجد")
    kafalah = ("Kafalah guarantee approved, certificate attached", "كفالة معتمدة والشهادة مرفقة") \
        if s.kafalah_guarantee else ("Not applied", "لم يُقدَّم")
    p.kv(_who(L) + [
        ("Requested amount (SAR)", "المبلغ المطلوب", f"{r.amount_sar:,.0f}"),
        ("Tenor (months)", "المدة بالأشهر", str(r.tenor_months)),
        ("Indicative profit rate", "هامش الربح الاسترشادي", f"{r.annual_profit_rate:.1%} per year"),
        ("Collateral", "الضمانات", f"{collateral[0]} / {collateral[1]}"),
        ("Kafalah guarantee", "كفالة", f"{kafalah[0]} / {kafalah[1]}"),
        ("Operating since", "بداية النشاط",
         conflict_value(plan, "APP_OPERATING_SINCE") or d(L.cr_issue_date)),
    ])
    p.section("Attachments", "المرفقات")
    att = ["Bank statement, 12 months / كشف حساب 12 شهراً", "Commercial registration / السجل التجاري",
           "Receivables aging / أعمار الذمم", "Tax compliance summary / ملخص الامتثال الضريبي"]
    att.append("Financial statements / القوائم المالية" if s.financial_statements_available
               else "Financial statements: not provided / القوائم المالية: غير مرفقة")
    p.set_font("dv", "", 9.5)
    for a in att:
        p.cell(0, 6.5, f"•  {a}", new_x="LMARGIN", new_y="NEXT")
    return p


def income_statement(L: Ledger, plan: NoisePlan) -> Doc:
    rev = sum(t.credit for t in L.statement if t.category == "revenue")
    inflated = conflict_value(plan, "INCOME_REVENUE_INFLATED")
    if inflated:
        rev = round(float(inflated) * 100)  # the business overstates revenue; the bank statement disagrees
    opex = sum(t.debit for t in L.statement if t.category == "opex")
    p = Doc("Income Statement (management accounts)", "قائمة الدخل (حسابات إدارية)",
            "Prepared by the business", "معدة من المنشأة")
    p.kv(_who(L)[:1] + [
        ("Period", "الفترة", f"{d(L.month_starts[0])} to {d(L.business.snapshot.as_of)}"),
        ("Revenue (SAR)", "الإيرادات", money(rev)),
        ("Operating expenses (SAR)", "المصروفات التشغيلية", money(opex)),
        ("Operating profit (SAR)", "الربح التشغيلي", money(rev - opex)),
    ])
    return p


def scan(pdf_bytes: bytes, rng: random.Random) -> bytes:
    """Turn a PDF into what a phone scan looks like: image only (no text layer),
    grey, slightly rotated, a little blurred and speckled."""
    import pypdfium2 as pdfium

    pages = []
    for page in pdfium.PdfDocument(pdf_bytes):
        img = page.render(scale=150 / 72).to_pil().convert("L")
        img = img.rotate(rng.uniform(-1.8, 1.8), resample=Image.BICUBIC, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.7)))
        noise = Image.effect_noise(img.size, rng.uniform(12, 22))
        img = Image.blend(img, noise, 0.08)
        pages.append(img)
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return buf.getvalue()


def render_all(b: SyntheticBusiness, folder: Path, level: Level = "clean") -> list[str]:
    """Write the business's documents at one difficulty level; returns the file names."""
    L = build_ledger(b)
    plan = plan_noise(b, level)
    docs = {
        "bank_statement": lambda: bank_statement(L, plan),
        "cr_certificate": lambda: cr_certificate(L, plan),
        "credit_report": lambda: credit_report(L),
        "receivables_aging": lambda: receivables_aging(L),
        "tax_compliance": lambda: tax_compliance(L),
        "financing_application": lambda: financing_application(L, plan),
    }
    if b.snapshot.financial_statements_available:
        docs["income_statement"] = lambda: income_statement(L, plan)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.pdf"):
        old.unlink()  # a re-render must not leave a document that should now be missing
    rng = random.Random(f"{b.meta.seed}-{level}-scan")
    written = []
    for name, make in docs.items():
        if name in plan.missing:
            continue
        data = bytes(make().output())
        if name in plan.scanned:
            data = scan(data, rng)
        (folder / f"{name}.pdf").write_bytes(data)
        written.append(f"{name}.pdf")
    (folder / "noise.json").write_text(json.dumps(plan.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return sorted(written)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "heldout", "demo", "all"], default="all")
    ap.add_argument("--level", choices=[*LEVELS, "all"], default="all")
    ap.add_argument("--data", type=Path, default=DATA_DIR)
    args = ap.parse_args()
    splits = ["dev", "heldout", "demo"] if args.split == "all" else [args.split]
    levels = list(LEVELS) if args.level == "all" else [args.level]
    for split in splits:
        folders = sorted(p for p in (args.data / split).iterdir() if (p / "business.json").exists())
        for f in folders:
            b = SyntheticBusiness.model_validate(json.loads((f / "business.json").read_text(encoding="utf-8")))
            for level in levels:
                render_all(b, f / "documents" / level, level)
        print(f"{split:<8} documents for {len(folders)} businesses, levels: {', '.join(levels)}")


if __name__ == "__main__":
    main()
