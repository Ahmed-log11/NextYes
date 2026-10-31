// English first, Arabic on the toggle. Every visible string lives here so the two stay in step.
import { createContext, useContext, useEffect, useState } from "react";
import { APP } from "./appStrings.js";

const STRINGS = {
  en: {
    nav: { how: "How it works", businesses: "For businesses", banks: "For banks", results: "Results", demo: "Try the demo" },
    hero: {
      title1: "Turn a bank's no",
      title2: "into a next yes.",
      body: "When a bank declines a small business's loan application, the reasons are often fixable, but the business often doesn't know which ones, or how to fix them. NextYes finds them using the bank's own rules, fixes what it can, follows up on the rest, and applies again when the business is ready.",
      startBusiness: "Start as a business",
      openBank: "Open the bank view",
      made1: "A concept for the",
      made2: "marketplace, built for the Future AI Builders hackathon. Not an official HUMAIN product.",
      g: { no: "Declined", read: "Read", diagnose: "Diagnose", fix: "Fix", apply: "Apply", yes: "Approved" },
    },
    story: {
      kicker: "How it works",
      title: "From the decline to the yes, in five stages",
      hint: "Hover or tap a stage",
      stages: [
        { t: "Consent", d: "The owner agrees once. Nothing is read or sent without it.",
          v: { a: "Read my documents", b: "Send only with my approval" } },
        { t: "Read", d: "Statements, registration, credit report and tax filings, in Arabic or English. Missing ones are fetched.",
          v: { a: "Bank statement", b: "Commercial registration", c: "Credit report", fetched: "fetched", ok: "read" } },
        { t: "Diagnose", d: "The bank's own rules score the business and name each reason, with its evidence.",
          v: { a: "Repayment cover below the bank's minimum", b: "Registration expires soon", ev: "evidence: statement, CR" } },
        { t: "Act", d: "The agent prepares every fix. The owner approves with a click; the agent follows up month by month.",
          v: { a: "Renew the registration online", approve: "Approve", later: "Not now" } },
        { t: "Apply", d: "When the business is ready, the full file goes to the bank, with every step on record.",
          v: { a: "Application approved", b: "Audit log attached" } },
      ],
    },
    doors: {
      business: { t: "I run a business", d: "Pick a demo business and watch the agent take it from declined to approved.", cta: "Start a journey" },
      bank: { t: "I work at a bank", d: "See the files owners chose to submit: the decision, the rules behind it, and the full audit log.", cta: "Open the bank view" },
      results: { t: "Does it work?", d: "Tested on 120 journeys across clean, realistic and hard paperwork. See what went wrong and what we changed.", cta: "See the results" },
    },
    foot: "Demo businesses and documents are simulated. Lender rules come from public sources and are marked where the threshold is ours.",
  },
  ar: {
    nav: { how: "كيف يعمل", businesses: "للمنشآت", banks: "للبنوك", results: "النتائج", demo: "جرّب العرض" },
    hero: {
      title1: "من «لا» البنك",
      title2: "إلى «نعم» القادمة.",
      body: "لما يرفض البنك طلب تمويل لمنشأة صغيرة، تكون الأسباب غالبًا قابلة للإصلاح، لكن المنشأة ما تعرف وش هي ولا كيف تصلحها. NextYes يكتشفها بقواعد البنك نفسه، ويصلّح اللي يقدر عليه، ويتابع الباقي، ويقدّم من جديد لما تجهز المنشأة.",
      startBusiness: "ابدأ كمنشأة",
      openBank: "افتح واجهة البنك",
      made1: "فكرة مقترحة لمنصة",
      made2: "مبنية لهاكاثون Future AI Builders، وليست منتجًا رسميًا من HUMAIN.",
      g: { no: "مرفوض", read: "قراءة", diagnose: "تشخيص", fix: "إصلاح", apply: "تقديم", yes: "مقبول" },
    },
    story: {
      kicker: "كيف يعمل",
      title: "من الرفض إلى القبول، في خمس مراحل",
      hint: "مرّر أو اضغط على المرحلة",
      stages: [
        { t: "الموافقة", d: "يوافق المالك مرة وحدة. ما يُقرأ ولا يُرسل شي بدونها.",
          v: { a: "اقرأ مستنداتي", b: "لا ترسل إلا بموافقتي" } },
        { t: "القراءة", d: "كشوف الحساب والسجل التجاري وتقرير الائتمان والإقرارات الضريبية، بالعربي أو الإنجليزي. والناقص يُجلب تلقائيًا.",
          v: { a: "كشف الحساب البنكي", b: "السجل التجاري", c: "تقرير الائتمان", fetched: "تم جلبه", ok: "تمت قراءته" } },
        { t: "التشخيص", d: "قواعد البنك نفسها تقيّم المنشأة وتسمّي كل سبب، مع دليله.",
          v: { a: "تغطية السداد أقل من حد البنك", b: "السجل التجاري ينتهي قريبًا", ev: "الدليل: الكشف، السجل" } },
        { t: "التنفيذ", d: "الوكيل يجهّز كل إصلاح، والمالك يوافق بضغطة، والوكيل يتابع شهرًا بشهر.",
          v: { a: "تجديد السجل التجاري إلكترونيًا", approve: "موافق", later: "ليس الآن" } },
        { t: "التقديم", d: "لما تجهز المنشأة، يروح الملف كامل للبنك، وكل خطوة موثّقة.",
          v: { a: "تمت الموافقة على الطلب", b: "سجل التدقيق مرفق" } },
      ],
    },
    doors: {
      business: { t: "أدير منشأة", d: "اختر منشأة تجريبية وشوف الوكيل ينقلها من الرفض إلى القبول.", cta: "ابدأ رحلة" },
      bank: { t: "أشتغل في بنك", d: "شوف الملفات اللي قرر أصحابها يقدمونها: القرار، والقواعد وراه، وسجل التدقيق كامل.", cta: "افتح واجهة البنك" },
      results: { t: "هل يشتغل فعلًا؟", d: "اختبرناه على 120 رحلة بمستندات نظيفة وواقعية وصعبة. شوف وين غلط ووش غيّرنا.", cta: "شوف النتائج" },
    },
    foot: "المنشآت والمستندات في العرض محاكاة. قواعد البنوك من مصادر عامة، ومعلَّم عليها لما يكون الحد من عندنا.",
  },
};

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem("ny-lang") || "en"; } catch { return "en"; }
  });
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    try { localStorage.setItem("ny-lang", lang); } catch { /* private mode */ }
  }, [lang]);
  return (
    <LangContext.Provider value={{ lang, setLang, t: { ...STRINGS[lang], app: APP[lang] }, rtl: lang === "ar" }}>
      {children}
    </LangContext.Provider>
  );
}

export const useLang = () => useContext(LangContext);

// For API values that come as {en, ar}
export const pick = (value, lang) => (value && typeof value === "object" ? value[lang] ?? value.en : value);
