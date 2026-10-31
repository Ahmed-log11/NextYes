// The plan as lanes: what needs the owner's click, what the agent is doing, what the team
// is doing, what only time fixes, and what is done.
import { useLang } from "../../lib/i18n.jsx";

const LANES = [
  ["approve", (s) => s.status === "awaiting_approval", "bg-amber"],
  ["agent", (s) => s.status === "in_progress" && s.executor === "agent", "bg-blue"],
  ["owner", (s) => s.status === "in_progress" && (s.executor === "owner" || s.executor === "approve"), "bg-blue-2"],
  ["wait", (s) => s.status === "in_progress" && s.executor === "wait", "bg-muted"],
  ["done", (s) => s.status === "done", "bg-teal"],
];

export default function Lanes({ journey, waiting, onAct, busy, onSelect }) {
  const { t, lang } = useLang();
  const pending = waiting?.pending ?? [];
  const L = t.app.lanes;
  return (
    <div className="flex flex-col gap-3">
      {journey.plan_summary && journey.steps.some((s) => s.status !== "done") && (
        <div className="rounded-2xl border border-line border-s-4 border-s-blue bg-white px-5 py-4 text-[14.5px] leading-relaxed">
          {journey.plan_summary[lang] ?? journey.plan_summary.en}
        </div>
      )}
      {LANES.map(([key, test, dot]) => {
        const steps = journey.steps.filter(test);
        if (!steps.length && key !== "approve") return null;
        return (
          <section key={key} className="rounded-2xl border border-line bg-white px-5 py-2">
            <header className="flex items-center gap-2.5 py-3">
              <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
              <h3 className="text-[15px] font-semibold">{L[key]}</h3>
              <span className="text-[13px] text-muted">{steps.length}</span>
              <span className="flex-1" />
              {key === "approve" && pending.length > 1 && (
                <button disabled={!!busy} onClick={() => onAct({ type: "approve", step_ids: pending })}
                  className="rounded-lg bg-blue px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-blue-2 disabled:opacity-50">{L.approveAll}</button>
              )}
            </header>
            {!steps.length && <p className="border-t border-line py-3 text-[13.5px] text-muted">{L.empty}</p>}
            {steps.map((s) => (
              <div key={s.step_id} className="grid grid-cols-[1fr_auto] items-center gap-4 border-t border-line py-3.5">
                <button className="min-w-0 text-start" onClick={() => onSelect(`f:${s.step_id}`)}>
                  <div className="text-[14.5px] font-semibold hover:text-blue">{s.title[lang] ?? s.title.en}</div>
                  <div className="mt-0.5 text-[13.5px] leading-snug text-muted">{s.detail[lang] ?? s.detail.en}</div>
                  {s.assignee && <div className="mt-1 text-[12.5px] text-blue">→ {[s.assignee.name, s.assignee.department].filter(Boolean).join(" · ")}</div>}
                </button>
                {pending.includes(s.step_id) && (
                  <div className="flex gap-2">
                    <button disabled={!!busy} onClick={() => onAct({ type: "approve", step_ids: [s.step_id] })}
                      className="rounded-lg bg-blue px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-blue-2 disabled:opacity-50">{t.app.detail.approve}</button>
                    <button disabled={!!busy} onClick={() => onAct({ type: "decline", step_ids: [s.step_id] })}
                      className="rounded-lg border border-line px-3 py-1.5 text-[13px] hover:bg-porcelain disabled:opacity-50">{t.app.detail.decline}</button>
                  </div>
                )}
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
