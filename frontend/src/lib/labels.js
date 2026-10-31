// Short names for codes that come from the backend, in both languages.
// The full explanation (with numbers) still comes from the API; these are the map labels.

export const BLOCKERS = {
  DSCR_LOW: { en: "Repayment cover too low", ar: "تغطية السداد منخفضة" },
  NO_SECURITY: { en: "No collateral or guarantee", ar: "لا يوجد ضمان أو كفالة" },
  CR_EXPIRING: { en: "Registration expiring", ar: "السجل التجاري قارب على الانتهاء" },
  CR_INVALID: { en: "Registration not active", ar: "السجل التجاري غير ساري" },
  RECEIVABLES_OVERDUE: { en: "Overdue invoices", ar: "فواتير متأخرة" },
  ACTIVE_DEFAULTS: { en: "Active default on record", ar: "تعثّر قائم في السجل الائتماني" },
  EINVOICING: { en: "E-invoicing not integrated", ar: "الفوترة الإلكترونية غير مربوطة" },
  VAT_LATE: { en: "Late VAT filings", ar: "تأخر في الإقرارات الضريبية" },
  CASHFLOW_VOLATILE: { en: "Revenue too uneven", ar: "الإيرادات متذبذبة" },
  HISTORY_SHORT: { en: "Too little operating history", ar: "مدة التشغيل قصيرة" },
  STATEMENTS_MISSING: { en: "No financial statements", ar: "لا توجد قوائم مالية" },
  ACCOUNTS_MIXED: { en: "Personal and business money mixed", ar: "خلط الحساب الشخصي بحساب المنشأة" },
  NOT_SME: { en: "Above the SME range", ar: "أكبر من نطاق المنشآت الصغيرة والمتوسطة" },
  REVENUE_LOW: { en: "Revenue below the minimum", ar: "الإيرادات أقل من الحد الأدنى" },
};

// The same rules named as what the bank checks (for the credit desk).
export const RULES = {
  DSCR_LOW: { en: "Repayment cover", ar: "تغطية السداد" },
  NO_SECURITY: { en: "Collateral or guarantee", ar: "ضمان أو كفالة" },
  CR_EXPIRING: { en: "Registration valid long enough", ar: "صلاحية السجل التجاري كافية" },
  CR_INVALID: { en: "Registration active", ar: "السجل التجاري ساري" },
  RECEIVABLES_OVERDUE: { en: "Overdue invoices within limit", ar: "الفواتير المتأخرة ضمن الحد" },
  ACTIVE_DEFAULTS: { en: "No active default", ar: "لا تعثّر قائم" },
  EINVOICING: { en: "E-invoicing integrated", ar: "الفوترة الإلكترونية مربوطة" },
  VAT_LATE: { en: "VAT filed on time", ar: "الإقرارات الضريبية في وقتها" },
  CASHFLOW_VOLATILE: { en: "Steady revenue", ar: "إيرادات مستقرة" },
  HISTORY_SHORT: { en: "Operating history", ar: "مدة التشغيل" },
  STATEMENTS_MISSING: { en: "Financial statements", ar: "القوائم المالية" },
  ACCOUNTS_MIXED: { en: "Separate business account", ar: "حساب منفصل للمنشأة" },
  NOT_SME: { en: "Within the SME range", ar: "ضمن نطاق المنشآت الصغيرة والمتوسطة" },
  REVENUE_LOW: { en: "Minimum revenue", ar: "الحد الأدنى للإيرادات" },
};

// Who carries out a step (backend "executor").
export const EXECUTORS = {
  agent: { en: "Agent does it", ar: "الوكيل ينفذها" },
  approve: { en: "Needs your approval", ar: "تحتاج موافقتك" },
  owner: { en: "You do it, agent follows up", ar: "أنت تنفذها والوكيل يتابع" },
  wait: { en: "Time; agent re-checks monthly", ar: "تحتاج وقت؛ الوكيل يراجع شهريًا" },
  advisor: { en: "Needs a human advisor", ar: "تحتاج مستشارًا بشريًا" },
};

// The department that usually handles a remedy. Shown as "suggested" until the owner assigns someone.
export const DEPARTMENTS = {
  RESIZE_REQUEST: { en: "Finance", ar: "المالية" },
  ADD_KAFALAH: { en: "Finance", ar: "المالية" },
  PREPARE_STATEMENTS: { en: "Accounting", ar: "المحاسبة" },
  OPEN_BUSINESS_ACCOUNT: { en: "Finance", ar: "المالية" },
  RENEW_CR: { en: "Government relations", ar: "العلاقات الحكومية" },
  CHASE_RECEIVABLES: { en: "NextYes agent", ar: "وكيل NextYes" },
  SETTLE_DEFAULT: { en: "Finance", ar: "المالية" },
  INTEGRATE_EINVOICING: { en: "IT & accounting", ar: "التقنية والمحاسبة" },
  FILE_VAT_ON_TIME: { en: "Accounting", ar: "المحاسبة" },
  STEADY_REVENUE: { en: "Sales", ar: "المبيعات" },
  WAIT_HISTORY: { en: "Time", ar: "الوقت" },
  SWITCH_LENDER: { en: "Owner", ar: "المالك" },
  ADVISOR: { en: "Human advisor", ar: "مستشار بشري" },
};

export const STATUS = {
  proposed: { en: "Proposed", ar: "مقترحة" },
  awaiting_approval: { en: "Awaiting approval", ar: "بانتظار موافقتك" },
  in_progress: { en: "In progress", ar: "قيد التنفيذ" },
  done: { en: "Done", ar: "تمت" },
  declined: { en: "Declined", ar: "مرفوضة" },
};

export const STAGES = {
  consent: { en: "Waiting for consent", ar: "بانتظار الموافقة" },
  awaiting_documents: { en: "Waiting for a document", ar: "بانتظار مستند" },
  working: { en: "Working on the plan", ar: "جاري تنفيذ الخطة" },
  awaiting_submit: { en: "Ready to apply", ar: "جاهز للتقديم" },
  submitted: { en: "Submitted", ar: "تم التقديم" },
  approved: { en: "Approved", ar: "تمت الموافقة" },
  no_consent: { en: "No consent given", ar: "لم تُعطَ الموافقة" },
  escalated: { en: "Handed to an advisor", ar: "حُوّل لمستشار" },
  not_reachable: { en: "Not reachable with known fixes", ar: "لا يمكن الوصول بالحلول المعروفة" },
  owner_declined: { en: "Owner declined the plan", ar: "رفض المالك الخطة" },
  out_of_time: { en: "Out of time", ar: "انتهى الوقت" },
};

export const DOCS = {
  bank_statement: { en: "Bank statement", ar: "كشف الحساب البنكي" },
  cr_certificate: { en: "Commercial registration", ar: "السجل التجاري" },
  credit_report: { en: "Credit report", ar: "تقرير الائتمان" },
  tax_compliance: { en: "Tax & Zakat compliance", ar: "الامتثال الضريبي والزكوي" },
  income_statement: { en: "Income statement", ar: "قائمة الدخل" },
  receivables_aging: { en: "Receivables aging", ar: "أعمار الذمم المدينة" },
  financing_application: { en: "Financing application", ar: "طلب التمويل" },
};

export const label = (table, code, lang) => table[code]?.[lang] ?? table[code]?.en ?? code.replaceAll("_", " ").toLowerCase();

export const sar = (n, lang) =>
  `${lang === "ar" ? "" : "SAR "}${Math.round(n).toLocaleString("en-US")}${lang === "ar" ? " ريال" : ""}`;
