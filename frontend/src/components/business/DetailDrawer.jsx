// Details for whatever node is selected on the map or the cards: the evidence behind an
// issue, what a fix does (approve / decline / assign), or what a department is handling.
import { useState } from "react";
import { useLang } from "../../lib/i18n.jsx";
import { BLOCKERS, EXECUTORS, STATUS, label } from "../../lib/labels.js";

const fmt = (v, lang) => {
  if (typeof v === "number") return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(v);
  if (typeof v === "boolean") return v ? (lang === "ar" ? "نعم" : "yes") : (lang === "ar" ? "لا" : "no");
  return String(v);
};

function Row({ k, v }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-line-dark py-2 text-[13px]">
      <span className="text-white/55">{k}</span><span className="text-end font-medium text-white" dir="auto">{v}</span>
    </div>
  );
}

function AssignForm({ step, onAct, busy }) {
  const { t } = useLang();
  const [name, setName] = useState(step.assignee?.name ?? "");
  const [dep, setDep] = useState(step.assignee?.department ?? "");
  const input = "w-full rounded-lg border border-line-dark bg-night px-3 py-2 text-[13.5px] text-white placeholder:text-white/35 focus:border-blue-2 focus:outline-none";
  return (
    <form className="mt-4 rounded-xl border border-line-dark bg-night/50 p-3"
      onSubmit={(e) => { e.preventDefault(); if (name.trim()) onAct({ type: "assign", step_id: step.step_id, name: name.trim(), department: dep.trim() }); }}>
      <p className="mb-2 text-[12.5px] font-semibold text-white/70">{t.app.detail.assign}</p>
      <div className="grid gap-2">
        <input className={input} placeholder={t.app.detail.name} value={name} onChange={(e) => setName(e.target.value)} />
        <input className={input} placeholder={t.app.detail.department} value={dep} onChange={(e) => setDep(e.target.value)} />
        <button disabled={!name.trim() || busy} className="rounded-lg bg-white/10 px-3 py-2 text-[13px] font-semibold text-white hover:bg-white/15 disabled:opacity-40">
          {t.app.detail.save}
        </button>
      </div>
    </form>
  );
}

export default function DetailDrawer({ node, graph, waiting, onAct, busy, onClose, onSelect }) {
  const { t, lang } = useLang();
  if (!node) return null;
  const d = t.app.detail;
  const pending = new Set(waiting?.pending ?? []);
  let kicker, title, body;

  if (node.type === "business") {
    kicker = t.app.band.score; title = node.title;
    body = (
      <>
        <Row k={t.app.band.score} v={`${Math.round(node.score)} / ${node.threshold}`} />
        <Row k={t.app.band.issues} v={graph.issues.filter((i) => !i.resolved).length} />
      </>
    );
  } else if (node.type === "issue") {
    const b = node.blocker;
    kicker = d.issue; title = label(BLOCKERS, b.code, lang);
    const fixes = graph.fixes.filter((f) => f.step.fixes.includes(b.code));
    body = (
      <>
        {lang === "en" || !b.message_ar ? <p className="text-[14px] leading-relaxed text-white/80" dir="ltr">{b.message}</p> : null}
        <p className="mt-4 text-[12px] font-semibold text-white/50">{d.evidence}</p>
        {Object.entries(b.evidence).map(([k, v]) => <Row key={k} k={k.replaceAll("_", " ")} v={fmt(v, lang)} />)}
        <p className="mt-4 text-[12px] font-semibold text-white/50">{d.source}</p>
        <p className="mt-1 text-[13px] leading-relaxed text-white/75" dir="ltr">{b.source}</p>
        {b.assumption && <p className="mt-2 rounded-lg bg-amber/10 px-3 py-2 text-[12.5px] text-[#F7C877]">{d.assumption}</p>}
        {fixes.length > 0 && <p className="mt-4 text-[12px] font-semibold text-white/50">{d.fix}</p>}
        {fixes.map((f) => (
          <button key={f.id} onClick={() => onSelect(f.id)} className="mt-1 block w-full rounded-lg border border-line-dark px-3 py-2 text-start text-[13px] text-white hover:border-blue-2">{f.title}</button>
        ))}
      </>
    );
  } else if (node.type === "fix") {
    const s = node.step;
    kicker = d.fix; title = node.title;
    body = (
      <>
        <p className="text-[14px] leading-relaxed text-white/80">{s.detail[lang] ?? s.detail.en}</p>
        <div className="mt-4">
          <Row k={d.status} v={label(STATUS, s.status, lang)} />
          <Row k={d.executor} v={label(EXECUTORS, s.executor, lang)} />
          <Row k={d.fixes} v={s.fixes.map((c) => label(BLOCKERS, c, lang)).join(" · ")} />
          {s.assignee && <Row k={d.assigned} v={[s.assignee.name, s.assignee.department].filter(Boolean).join(" · ")} />}
        </div>
        {pending.has(s.step_id) && (
          <div className="mt-4 flex gap-2">
            <button disabled={!!busy} onClick={() => onAct({ type: "approve", step_ids: [s.step_id] })}
              className="flex-1 rounded-lg bg-blue px-3 py-2.5 text-[14px] font-semibold text-white hover:bg-blue-2 disabled:opacity-50">{d.approve}</button>
            <button disabled={!!busy} onClick={() => onAct({ type: "decline", step_ids: [s.step_id] })}
              className="rounded-lg border border-white/20 px-3 py-2.5 text-[14px] text-white/80 hover:bg-white/5 disabled:opacity-50">{d.decline}</button>
          </div>
        )}
        {s.status !== "done" && s.executor !== "wait" && <AssignForm key={s.step_id} step={s} onAct={onAct} busy={busy} />}
      </>
    );
  } else {
    kicker = d.who; title = node.title;
    const fixes = graph.fixes.filter((f) => node.fixIds.includes(f.id));
    body = (
      <>
        {node.people.length > 0 && <Row k={d.assigned} v={node.people.join(", ")} />}
        {node.suggested && <p className="text-[13px] text-white/60">{t.app.map.suggested}</p>}
        <p className="mt-4 text-[12px] font-semibold text-white/50">{d.steps}</p>
        {fixes.map((f) => (
          <button key={f.id} onClick={() => onSelect(f.id)} className="mt-1 flex w-full items-center justify-between gap-2 rounded-lg border border-line-dark px-3 py-2 text-start text-[13px] text-white hover:border-blue-2">
            <span>{f.title}</span><span className="flex-none text-[11px] text-white/50">{label(STATUS, f.status, lang)}</span>
          </button>
        ))}
      </>
    );
  }

  return (
    <aside className="absolute inset-y-0 end-0 z-10 flex w-full max-w-[380px] flex-col border-s border-line-dark bg-night-2/97 shadow-2xl backdrop-blur"
      style={{ animation: "drawer-in .25s ease-out" }}>
      <div className="flex items-start justify-between gap-3 border-b border-line-dark p-5">
        <div>
          <p className="text-[12px] font-semibold text-blue-2">{kicker}</p>
          <h3 className="mt-1 text-[17px] font-semibold leading-snug text-white">{title}</h3>
        </div>
        <button onClick={onClose} aria-label={d.close} className="rounded-lg p-1.5 text-white/60 hover:bg-white/10 hover:text-white">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">{body}</div>
    </aside>
  );
}
