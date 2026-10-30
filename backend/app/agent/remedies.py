"""What can be done about each reason for a decline, who does it, and what it changes.

Each remedy names the blocker codes it fixes (the policy rule ids), its executor, and
its effect on the business's data, so the simulator can play the journey forward month
by month and the engine can re-assess the result.

Two kinds of effect:
- one-off: applied once, `duration` months after the step starts (0 = immediately);
- ongoing: applied every month while the step runs, until `done_when` holds
  (e.g. chasing overdue invoices until the overdue share is under the lender's limit).

Durations and collection rates are our assumptions for the simulation, stated here
so they can be questioned: CR renewal is online and immediate; a Kafalah guarantee
takes a month; a new business account needs two months of use before lenders count it;
the next VAT quarter must be filed on time (three months); chasing collects half of
what is still overdue each month.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import mean, pstdev
from typing import Any, Callable

from ..engine import FinancialSnapshot, Policy, finance
from .models import Executor, Text

Snap = FinancialSnapshot
Params = dict[str, Any]

COLLECTION_RATE = 0.5      # share of the remaining overdue receivables collected per month of chasing
RESIZE_SAFETY = 0.98       # request slightly under the maximum, so small changes don't flip the verdict
MIN_USEFUL_AMOUNT = 50_000  # below this a resized request is not worth applying for
MAX_MONTHS = 12            # longer than this counts as "not reachable" for planning


def rule_params(policy: Policy, check: str) -> Params | None:
    return next((r.params for r in policy.rules if r.check == check), None)


def _cv(rev: list[float]) -> float:
    m = mean(rev)
    return pstdev(rev) / m if m else float("inf")


@dataclass(frozen=True)
class Remedy:
    id: str
    fixes: tuple[str, ...]
    executor: Executor
    title: Text
    detail: Callable[[Snap, Policy, Params], Text]
    params: Callable[[Snap, Policy], Params] = lambda s, p: {}
    applicable: Callable[[Snap, Policy], bool] = lambda s, p: True
    duration: Callable[[Snap, Policy, Params], int] = lambda s, p, prm: 0
    on_done: Callable[[Snap, Params], Snap] = lambda s, prm: s
    monthly: Callable[[Snap, Params], Snap] | None = None          # ongoing effect
    done_when: Callable[[Snap, Policy, Params], bool] | None = None  # ongoing: finished when true
    notes: tuple[str, ...] = field(default_factory=tuple)


def _t(en: str, ar: str) -> Text:
    return Text(en=en, ar=ar)


# ---------------------------------------------------------------- one-off remedies

def _renew_cr(s: Snap, prm: Params) -> Snap:
    base = max(s.cr_expiry, s.as_of)
    return s.model_copy(update={"cr_active": True, "cr_expiry": base + timedelta(days=365)})


def _resize_params(s: Snap, p: Policy) -> Params:
    min_dscr = (rule_params(p, "dscr_min") or {"min_dscr": 1.2})["min_dscr"]
    cap = finance.max_affordable_amount(s, min_dscr) * RESIZE_SAFETY
    return {"amount_sar": float(max(math.floor(cap / 10_000) * 10_000, 0)),
            "previous_sar": s.request.amount_sar}


def _resize(s: Snap, prm: Params) -> Snap:
    return s.model_copy(update={"request": s.request.model_copy(update={"amount_sar": prm["amount_sar"]})})


def _set(field_name: str, value: Any) -> Callable[[Snap, Params], Snap]:
    return lambda s, prm: s.model_copy(update={field_name: value})


# ---------------------------------------------------------------- ongoing remedies

def _chase_monthly(s: Snap, prm: Params) -> Snap:
    collected = round(s.receivables_overdue_90d_sar * COLLECTION_RATE, 2)
    return s.model_copy(update={
        "receivables_overdue_90d_sar": round(s.receivables_overdue_90d_sar - collected, 2),
        "receivables_outstanding_sar": round(s.receivables_outstanding_sar - collected, 2),
    })


def _chase_done(s: Snap, p: Policy, prm: Params) -> bool:
    limit = (rule_params(p, "receivables_overdue") or {"max_ratio": 1.0})["max_ratio"]
    return s.overdue_receivables_ratio <= limit


def _chase_months(s: Snap, p: Policy, prm: Params) -> int:
    for k in range(MAX_MONTHS + 1):
        if _chase_done(s, p, prm):
            return k
        s = _chase_monthly(s, prm)
    return MAX_MONTHS + 1


def _stable_done(s: Snap, p: Policy, prm: Params) -> bool:
    lim = rule_params(p, "cashflow_consistency") or {"max_cv": 1.0, "max_zero_months": 12}
    return s.revenue_cv <= lim["max_cv"] and s.zero_revenue_months <= lim["max_zero_months"]


def _stable_months(s: Snap, p: Policy, prm: Params) -> int:
    rev = list(s.monthly_revenue_sar)
    for k in range(MAX_MONTHS + 1):
        if _stable_done(s.model_copy(update={"monthly_revenue_sar": rev}), p, prm):
            return k
        rev = rev[1:] + [round(mean(rev), 2)]  # what steady revenue does to the 12-month window
    return MAX_MONTHS + 1


def _history_done(s: Snap, p: Policy, prm: Params) -> bool:
    return s.operating_months >= (rule_params(p, "min_operating_history") or {"min_months": 0})["min_months"]


def _history_months(s: Snap, p: Policy, prm: Params) -> int:
    need = (rule_params(p, "min_operating_history") or {"min_months": 0})["min_months"]
    return max(need - s.operating_months, 0)


def _sar(x: float) -> str:
    return f"SAR {x:,.0f}"


# ---------------------------------------------------------------- the catalog

CATALOG: dict[str, Remedy] = {r.id: r for r in [
    Remedy(
        "RENEW_CR", ("CR_INVALID", "CR_EXPIRING"), "approve",
        _t("Renew the commercial registration", "تجديد السجل التجاري"),
        lambda s, p, prm: _t(f"Prepared the online renewal; the registration will run to {_renew_cr(s, prm).cr_expiry}.",
                             f"جهّزنا طلب التجديد الإلكتروني؛ سيصبح السجل ساريًا حتى {_renew_cr(s, prm).cr_expiry}."),
        duration=lambda s, p, prm: 0 if s.cr_active else 1,  # a suspended CR takes a month to reactivate
        on_done=_renew_cr,
    ),
    Remedy(
        "RESIZE_REQUEST", ("DSCR_LOW",), "approve",
        _t("Request an amount the cash flow can repay", "طلب مبلغ يتحمّله التدفق النقدي"),
        lambda s, p, prm: _t(
            f"Lower the request from {_sar(prm['previous_sar'])} to {_sar(prm['amount_sar'])}, "
            f"the most the current cash flow can repay at this tenor.",
            f"تخفيض المبلغ المطلوب من {_sar(prm['previous_sar'])} إلى {_sar(prm['amount_sar'])}، "
            f"وهو أعلى مبلغ يمكن سداده بالتدفق النقدي الحالي لنفس المدة."),
        params=_resize_params,
        applicable=lambda s, p: _resize_params(s, p)["amount_sar"] >= MIN_USEFUL_AMOUNT,
        on_done=_resize,
    ),
    Remedy(
        "ADD_KAFALAH", ("NO_SECURITY",), "approve",
        _t("Apply for a Kafalah guarantee", "التقديم على ضمان كفالة"),
        lambda s, p, prm: _t("Prepared the Kafalah guarantee application from the documents on file; approval takes about a month.",
                             "جهّزنا طلب ضمان كفالة من المستندات المتوفرة؛ تستغرق الموافقة نحو شهر."),
        applicable=lambda s, p: finance.size_class(s.annual_revenue_sar) != "not_sme",
        duration=lambda s, p, prm: 1,
        on_done=_set("kafalah_guarantee", True),
    ),
    Remedy(
        "PREPARE_STATEMENTS", ("STATEMENTS_MISSING",), "approve",
        _t("Prepare management accounts", "إعداد القوائم المالية الإدارية"),
        lambda s, p, prm: _t("Drafted an income statement and balance sheet from the bank statement for the owner to review and sign.",
                             "أعددنا قائمة دخل وميزانية من كشف الحساب ليراجعها المالك ويوقّعها."),
        on_done=_set("financial_statements_available", True),
    ),
    Remedy(
        "OPEN_BUSINESS_ACCOUNT", ("ACCOUNTS_MIXED",), "approve",
        _t("Open a separate business account", "فتح حساب تجاري مستقل"),
        lambda s, p, prm: _t("Prepared the business account application; lenders count it after about two months of use.",
                             "جهّزنا طلب فتح الحساب التجاري؛ يعتدّ به الممولون بعد نحو شهرين من الاستخدام."),
        duration=lambda s, p, prm: 2,
        on_done=_set("separate_business_account", True),
    ),
    Remedy(
        "CHASE_RECEIVABLES", ("RECEIVABLES_OVERDUE",), "agent",
        _t("Collect overdue invoices", "تحصيل الفواتير المتأخرة"),
        lambda s, p, prm: _t(
            f"Sending payment reminders for {_sar(s.receivables_overdue_90d_sar)} overdue more than 90 days, every month until the overdue share is within the lender's limit.",
            f"إرسال تذكيرات سداد لمبلغ {_sar(s.receivables_overdue_90d_sar)} متأخر أكثر من 90 يومًا، شهريًا حتى تصبح نسبة المتأخرات ضمن حد الممول."),
        duration=_chase_months, monthly=_chase_monthly, done_when=_chase_done,
    ),
    Remedy(
        "SETTLE_DEFAULT", ("ACTIVE_DEFAULTS",), "owner",
        _t("Settle the defaulted facility", "تسوية التسهيل المتعثر"),
        lambda s, p, prm: _t("The owner settles or reschedules the defaulted facility; we will follow up and request the updated credit report.",
                             "يسوّي المالك التسهيل المتعثر أو يعيد جدولته؛ سنتابع ونطلب تقريرًا ائتمانيًا محدّثًا."),
        duration=lambda s, p, prm: 1,
        on_done=_set("has_active_defaults", False),
    ),
    Remedy(
        "INTEGRATE_EINVOICING", ("EINVOICING",), "owner",
        _t("Connect e-invoicing (ZATCA phase 2)", "الربط بالفوترة الإلكترونية (المرحلة الثانية)"),
        lambda s, p, prm: _t("The owner connects the invoicing system to ZATCA through an approved provider; we will check the status monthly.",
                             "يربط المالك نظام الفوترة مع الهيئة عبر مزوّد معتمد؛ سنتحقق من الحالة شهريًا."),
        duration=lambda s, p, prm: 1,
        on_done=_set("einvoicing_compliant", True),
    ),
    Remedy(
        "FILE_VAT_ON_TIME", ("VAT_LATE",), "owner",
        _t("File the next VAT return on time", "تقديم إقرار الضريبة القادم في موعده"),
        lambda s, p, prm: _t("The next quarterly VAT return must be filed before its due date; we will send reminders.",
                             "يجب تقديم إقرار ضريبة القيمة المضافة القادم قبل موعده؛ سنرسل تذكيرات."),
        duration=lambda s, p, prm: 3,
        on_done=_set("vat_filed_on_time", True),
    ),
    Remedy(
        "STEADY_REVENUE", ("CASHFLOW_VOLATILE",), "owner",
        _t("Steady the monthly revenue", "استقرار الإيراد الشهري"),
        lambda s, p, prm: _t("Move customers to regular monthly billing or contracts; we track the revenue variation every month.",
                             "تحويل العملاء إلى فوترة شهرية منتظمة أو عقود؛ نتابع تذبذب الإيراد كل شهر."),
        duration=_stable_months, done_when=_stable_done,
        monthly=lambda s, prm: s,  # the effect is in the simulator's revenue roll (steady months)
    ),
    Remedy(
        "WAIT_HISTORY", ("HISTORY_SHORT",), "wait",
        _t("Build operating history", "اكتساب سجل تشغيلي كافٍ"),
        lambda s, p, prm: _t(f"This lender needs more operating history; about {_history_months(s, p, prm)} more months.",
                             f"يحتاج هذا الممول سجلًا تشغيليًا أطول؛ نحو {_history_months(s, p, prm)} أشهر إضافية."),
        duration=_history_months, done_when=_history_done, monthly=lambda s, prm: s,
    ),
]}

# Moving the application to a lender whose criteria the business meets. The planner
# builds it (it needs both lenders' names); its effect is on the journey, not the data.
CATALOG["SWITCH_LENDER"] = Remedy(
    "SWITCH_LENDER", (), "approve",
    _t("Apply to a better-fitting lender", "التقديم لممول أنسب"),
    lambda s, p, prm: _t(f"Apply to {prm['to_name_en']} instead of {prm['from_name_en']}: "
                         f"the business meets its criteria sooner ({prm['reason_en']}).",
                         f"التقديم إلى {prm['to_name_ar']} بدلًا من {prm['from_name_ar']}: "
                         f"المنشأة تستوفي معاييره أسرع ({prm['reason_ar']})."),
)

# Blockers no remedy can fix within a journey: a human advisor takes over.
ESCALATE = {
    "NOT_SME": _t("Revenue is above the SME range; a corporate banking advisor should take over.",
                  "الإيراد أعلى من نطاق المنشآت الصغيرة والمتوسطة؛ يتولى الأمر مستشار الخدمات المصرفية للشركات."),
    "REVENUE_LOW": _t("Annual revenue is below this lender's minimum; growing revenue takes longer than this journey.",
                      "الإيراد السنوي أقل من الحد الأدنى لهذا الممول؛ ونموّه يحتاج وقتًا أطول من هذه الرحلة."),
}

# Steps the agent must never propose, whatever it is asked (checked by the plan validator).
FORBIDDEN = {
    "HIDE_DEBT": "Hiding an existing facility from the lender",
    "ALTER_DOCUMENT": "Changing figures in a document",
    "SPLIT_APPLICATIONS": "Splitting one need into several applications to avoid checks",
    "BORROWED_DEPOSITS": "Parking borrowed money in the account to inflate revenue",
}


def remedies_for(code: str) -> list[Remedy]:
    return [r for r in CATALOG.values() if code in r.fixes]
