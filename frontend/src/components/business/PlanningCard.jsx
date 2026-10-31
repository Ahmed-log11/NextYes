// How the current plan was chosen: the agent proposed one, the rule planner made one, the
// simulator played both forward, and the better one runs (journey.planning, from the API).
import { useLang } from "../../lib/i18n.jsx";

const WHY_AR = {
  "the agent's plan projects a better outcome than the rule plan": "خطة الوكيل توصل لنتيجة أفضل من خطة القواعد",
  "the agent's plan is valid and projects the same outcome as the rule plan": "خطة الوكيل صحيحة وتوصل لنفس نتيجة خطة القواعد",
  "the rule plan projects a better outcome than the agent's plan": "خطة القواعد توصل لنتيجة أفضل من خطة الوكيل",
  "neither plan reaches the threshold; the rule plan was kept": "ولا خطة توصل للحد المطلوب؛ بقيت خطة القواعد",
  "the agent's plan failed validation twice; the rule plan was used": "خطة الوكيل ما اجتازت الفحص مرتين؛ استُخدمت خطة القواعد",
  "the model was unavailable; the rule plan was used": "النموذج ما كان متاح؛ استُخدمت خطة القواعد",
};

function Outcome({ title, p, win, t }) {
  const P = t.app.planning;
  return (
    <div className={`rounded-xl border px-4 py-3 ${win ? "border-blue bg-blue-soft/40" : "border-line"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold">{title}</span>
        {win && <span className="rounded-md bg-blue px-2 py-0.5 text-[11px] font-semibold text-white">{P.used}</span>}
      </div>
      {p ? (
        <p className="mt-1 text-[13px] text-muted">
          {p.ready ? `${P.readyIn} ${p.months} ${P.months} · ${p.owner_actions} ${P.ownerActions}` : P.notReady}
        </p>
      ) : <p className="mt-1 text-[13px] text-muted">{P.noPlan}</p>}
    </div>
  );
}

export default function PlanningCard({ journey }) {
  const { t, lang } = useLang();
  const P = t.app.planning;
  const last = [...(journey.planning ?? [])].reverse().find((r) => r.rules);
  if (!last) return null;
  const agentWon = last.source === "agent";
  return (
    <section className="rounded-2xl border border-line bg-white px-5 py-4">
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold">{P.title}</h3>
        <span className="text-[12.5px] text-muted">· {P.month} {last.month}</span>
      </header>
      <p className="mt-1 text-[13.5px] text-muted">{lang === "ar" ? WHY_AR[last.why] ?? last.why : last.why.charAt(0).toUpperCase() + last.why.slice(1)}.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Outcome title={P.agent} p={last.agent} win={agentWon} t={t} />
        <Outcome title={P.rules} p={last.rules} win={!agentWon} t={t} />
      </div>
      {last.reasoning && (
        <p className="mt-3 rounded-lg bg-porcelain px-3 py-2 text-[13px] leading-relaxed" dir="auto">
          <span className="font-semibold">{P.reasoning}: </span>{last.reasoning}
        </p>
      )}
      {last.agent_issues?.length > 0 && (
        <p className="mt-2 text-[12.5px] text-[#9A6411]" dir="ltr">{P.issues}: {last.agent_issues.join("; ")}</p>
      )}
      <p className="mt-2 text-[12px] text-muted">{P.note}</p>
    </section>
  );
}
