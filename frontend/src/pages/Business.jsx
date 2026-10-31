// The business owner's screen. Before a journey: pick the paperwork level and start.
// Then consent, then the readiness band, the map (or cards), the plan lanes and the chat.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell.jsx";
import ReadinessMap from "../components/business/ReadinessMap.jsx";
import ReadinessCards from "../components/business/ReadinessCards.jsx";
import DetailDrawer from "../components/business/DetailDrawer.jsx";
import Lanes from "../components/business/Lanes.jsx";
import PlanningCard from "../components/business/PlanningCard.jsx";
import SidePanel from "../components/business/SidePanel.jsx";
import { buildGraph, findNode } from "../components/business/graph.js";
import { useLang, pick } from "../lib/i18n.jsx";
import { useDemo, useJourney } from "../lib/store.jsx";
import { api } from "../lib/api.js";
import { DOCS, STAGES, label, sar } from "../lib/labels.js";

const TERMINAL_OK = new Set(["approved"]);

function Spinner({ className = "" }) {
  return <span className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />;
}

function StartPanel({ business, onStarted }) {
  const { t, lang } = useLang();
  const [level, setLevel] = useState("realistic");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const s = t.app.start;
  const go = async () => {
    setBusy(true); setErr(null);
    try { const d = await api.start(business.business_id, level); onStarted(d); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="relative overflow-hidden rounded-3xl bg-night p-8 text-white md:p-10">
      <div className="grid-bg pointer-events-none absolute inset-0 opacity-60" />
      <div className="pointer-events-none absolute -top-32 h-80 w-[520px] rounded-full bg-blue/30 blur-[90px] end-0" />
      <div className="relative grid gap-10 lg:grid-cols-[1fr_420px]">
        <div>
          <p className="text-[13px] font-semibold text-blue-2">{pick(business.sector, lang)} · {pick(business.city, lang)}</p>
          <h1 className="display mt-2 text-[34px] font-bold leading-tight">{pick(business.name, lang)}</h1>
          <p className="mt-2 text-[16px] text-white/70">{sar(business.request.amount_sar, lang)} · {business.request.tenor_months} {lang === "ar" ? "شهرًا" : "months"}</p>
          <h2 className="mt-8 text-[19px] font-semibold">{s.title}</h2>
          <p className="mt-2 max-w-[520px] text-[15px] leading-relaxed text-white/65">{s.body}</p>
        </div>
        <div className="rounded-2xl border border-line-dark bg-night-2/80 p-5">
          <p className="text-[13px] font-semibold text-white/70">{s.level}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-white/50">{s.levelNote}</p>
          <div className="mt-3 grid gap-2">
            {business.levels.map((lv) => (
              <button key={lv} onClick={() => setLevel(lv)}
                className={`rounded-xl border px-4 py-3 text-start transition-colors ${level === lv ? "border-blue-2 bg-blue/15" : "border-line-dark hover:border-white/30"}`}>
                <span className="block text-[14.5px] font-semibold">{s.levels[lv]}</span>
                <span className="block text-[12.5px] text-white/55">{s.levelHint[lv]}</span>
              </button>
            ))}
          </div>
          <button onClick={go} disabled={busy}
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-blue px-5 py-3.5 text-[15px] font-semibold hover:bg-blue-2 disabled:opacity-60">
            {busy && <Spinner />} {s.go}
          </button>
          {err && <p className="mt-3 text-[13px] text-[#FF9EA1]">{err}</p>}
        </div>
      </div>
    </div>
  );
}

function ConsentPanel({ waiting, onAct, busy }) {
  const { t, lang } = useLang();
  const c = t.app.consent;
  return (
    <div className="mx-auto max-w-[720px] rounded-3xl border border-line bg-white p-8 shadow-[0_30px_60px_-40px_rgba(13,27,42,.4)]">
      <h2 className="display text-[26px] font-bold">{c.title}</h2>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{c.body}</p>
      <ul className="mt-5 grid gap-2 sm:grid-cols-2">
        {(waiting.sources ?? []).map((s, i) => (
          <li key={i} className="flex items-center gap-2.5 rounded-xl bg-porcelain px-3.5 py-2.5 text-[14px]">
            <span className="h-2 w-2 rounded-full bg-blue" />{pick(s, lang)}
          </li>
        ))}
      </ul>
      {busy === "consent" ? (
        <div className="mt-7 rounded-2xl bg-night p-5 text-white">
          <div className="flex items-center gap-3 text-[15px] font-semibold"><Spinner className="text-blue-2" /> {c.reading}</div>
          <p className="mt-2 text-[13px] text-white/60">{c.readingHint}</p>
          <div className="mt-4 h-1 overflow-hidden rounded-full bg-white/10"><span className="block h-full w-1/3 rounded-full bg-blue-2" style={{ animation: "fill-bar 40s ease-out forwards" }} /></div>
        </div>
      ) : (
        <div className="mt-7 flex gap-3">
          <button onClick={() => onAct({ type: "consent", given: true })} className="rounded-xl bg-blue px-5 py-3 text-[15px] font-semibold text-white hover:bg-blue-2">{c.yes}</button>
          <button onClick={() => onAct({ type: "consent", given: false })} className="rounded-xl border border-line px-5 py-3 text-[15px]">{c.no}</button>
        </div>
      )}
    </div>
  );
}

function Band({ journey }) {
  const { t, lang } = useLang();
  const a = journey.assessment;
  const hist = journey.history ?? [];
  if (!a) return null;
  const ok = a.score >= a.threshold;
  return (
    <div className="relative overflow-hidden rounded-3xl bg-night px-6 py-6 text-white md:px-8">
      <div className="pointer-events-none absolute -top-24 h-64 w-[600px] rounded-full bg-blue/30 blur-[90px] end-0" />
      <div className="relative grid items-center gap-6 lg:grid-cols-[minmax(260px,340px)_1fr_auto]">
        <div>
          <p className="text-[13px] text-white/55">{t.app.band.score}</p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="display text-[60px] font-bold leading-none">{Math.round(a.score)}</span>
            <span className="text-[20px] text-white/45">/ {a.threshold} {t.app.band.needs}</span>
          </div>
          <div className="relative mt-4 h-2 rounded-full bg-white/10">
            <span className={`absolute inset-y-0 start-0 rounded-full transition-all duration-700 ${ok ? "bg-teal" : "bg-gradient-to-r from-amber to-[#F7C877]"}`} style={{ width: `${Math.min(100, a.score)}%` }} />
            <span className="absolute -top-1.5 h-5 w-0.5 bg-white" style={{ insetInlineStart: `${a.threshold}%` }} />
          </div>
        </div>
        {/* score over the months, as small steps */}
        <div className="flex items-end gap-2">
          {hist.map((h, i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <span className="text-[11.5px] text-white/60">{Math.round(h.score)}</span>
              <span className={`w-9 rounded-md ${h.score >= h.threshold ? "bg-teal" : "bg-blue-2/70"}`} style={{ height: `${Math.max(8, h.score * 0.6)}px` }} />
              <span className="text-[11px] text-white/45">{lang === "ar" ? "ش" : "M"}{h.month}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 lg:flex-col lg:items-end">
          <span className={`rounded-lg px-3 py-1.5 text-[13px] font-semibold ${TERMINAL_OK.has(journey.stage) || journey.stage === "awaiting_submit" ? "bg-teal/20 text-[#5EE3C9]" : "bg-white/10 text-white/85"}`}>
            {label(STAGES, journey.stage, lang)}
          </span>
          <span className="text-[13px] text-white/55">{t.app.band.month} {journey.month} · {pick(a.policy_name, lang)}</span>
        </div>
      </div>
    </div>
  );
}

function FlowBar({ journey, waiting, onAct, busy }) {
  const { t } = useLang();
  const f = t.app.flow;
  if (journey.stage === "approved") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-teal px-6 py-5 text-white">
        <div><p className="text-[18px] font-bold">✓ {f.approved}</p><p className="text-[14px] text-white/85">{f.approvedBody}</p></div>
        <Link to="/bank" className="rounded-xl bg-white px-4 py-2.5 text-[14px] font-semibold text-[#0B7A68]">{f.bankView}</Link>
      </div>
    );
  }
  if (!waiting) return <div className="rounded-2xl border border-line bg-white px-6 py-4 text-[14px] text-muted">{f.ended} · {label(STAGES, journey.stage, "en")}</div>;
  if (waiting.await === "submit") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-night px-6 py-5 text-white">
        <div><p className="text-[16px] font-semibold">{t.app.band.ready}</p><p className="text-[13.5px] text-white/60">{f.submitHint}</p></div>
        <div className="flex gap-2">
          <button disabled={!!busy} onClick={() => onAct({ type: "submit", approve: true })} className="flex items-center gap-2 rounded-xl bg-teal px-5 py-3 text-[15px] font-semibold disabled:opacity-60">{busy === "submit" && <Spinner />}{f.submit}</button>
          <button disabled={!!busy} onClick={() => onAct({ type: "submit", approve: false })} className="rounded-xl border border-white/25 px-4 py-3 text-[14px]">{f.hold}</button>
        </div>
      </div>
    );
  }
  if (waiting.await === "owner") {
    const blocked = (waiting.pending ?? []).length > 0;
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-night px-6 py-4 text-white">
        <p className="text-[13.5px] text-white/65">{f.advanceHint}</p>
        <button disabled={!!busy} onClick={() => onAct({ type: "advance_month" })}
          className={`flex items-center gap-2 rounded-xl px-5 py-3 text-[15px] font-semibold disabled:opacity-60 ${blocked ? "border border-white/25" : "bg-blue hover:bg-blue-2"}`}>
          {busy === "advance_month" && <Spinner />}{f.advance} →
        </button>
      </div>
    );
  }
  return null;
}

function DocumentsMissing({ waiting, onAct, busy }) {
  const { t, lang } = useLang();
  return (
    <div className="mx-auto max-w-[640px] rounded-3xl border border-line bg-white p-8">
      <h2 className="text-[22px] font-bold">{t.app.docsMissing.title}</h2>
      <p className="mt-2 text-[15px] text-muted">{t.app.docsMissing.body}</p>
      {waiting.missing.map((d) => (
        <div key={d} className="mt-4 flex items-center justify-between rounded-xl bg-porcelain px-4 py-3">
          <span className="font-semibold">{label(DOCS, d, lang)}</span>
          <button disabled={!!busy} onClick={() => onAct({ type: "upload", documents: [d] })} className="rounded-lg bg-blue px-4 py-2 text-[14px] font-semibold text-white">{t.app.docsMissing.upload}</button>
        </div>
      ))}
    </div>
  );
}

function Journey({ journeyId, onRestart }) {
  const { t, lang } = useLang();
  const { journey, waiting, act, busy, error } = useJourney(journeyId);
  const [view, setView] = useState("map");
  const [selected, setSelected] = useState(null);
  const graph = useMemo(() => (journey?.assessment ? buildGraph(journey, lang) : null), [journey, lang]);
  const node = graph && selected ? findNode(graph, selected) : null;

  if (error && !journey) return <p className="rounded-xl bg-coral-soft px-4 py-3 text-[#B4282D]">{error} <button className="underline" onClick={onRestart}>{t.app.start.restart}</button></p>;
  if (!journey) return <div className="h-64 animate-pulse rounded-3xl bg-white" />;
  if (waiting?.await === "consent") return <ConsentPanel waiting={waiting} onAct={act} busy={busy} />;
  if (waiting?.await === "documents") return <DocumentsMissing waiting={waiting} onAct={act} busy={busy} />;

  const m = t.app.map;
  return (
    <div className="flex flex-col gap-5">
      <Band journey={journey} />
      {error && <p className="rounded-xl bg-coral-soft px-4 py-3 text-[14px] text-[#B4282D]">{error}</p>}

      {graph && (
        <section className="relative overflow-hidden rounded-3xl bg-night text-white">
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-50" />
          <header className="relative flex flex-wrap items-end justify-between gap-4 px-6 pb-2 pt-6 md:px-8">
            <div>
              <h2 className="display text-[22px] font-bold">{m.title}</h2>
              <p className="mt-1 text-[14px] text-white/60">{m.sub}</p>
              {(() => {
                const last = [...(journey.planning ?? [])].reverse().find((r) => r.rules);
                if (!last) return null;
                return (
                  <span className={`mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[12px] font-semibold ${
                    last.source === "agent" ? "bg-blue/25 text-[#AFC2FF]" : "bg-white/10 text-white/70"}`}>
                    {last.source === "agent" ? t.app.planning.badgeAgent : t.app.planning.badgeRules}
                  </span>
                );
              })()}
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden text-[12.5px] text-white/40 sm:inline">{m.hint}</span>
              <div className="flex rounded-xl border border-line-dark bg-night-2 p-1" role="tablist">
                {[["map", m.asMap], ["cards", m.asCards]].map(([k, v]) => (
                  <button key={k} role="tab" aria-selected={view === k} onClick={() => setView(k)}
                    className={`rounded-lg px-3.5 py-1.5 text-[13px] font-semibold transition-colors ${view === k ? "bg-blue text-white" : "text-white/60 hover:text-white"}`}>{v}</button>
                ))}
              </div>
            </div>
          </header>
          <div className={`relative px-4 pb-6 pt-3 md:px-6 ${view === "map" || node ? "min-h-[460px]" : ""}`}>
            {graph.issues.length === 0 ? <p className="px-2 py-10 text-[15px] text-white/70">{m.noIssues}</p>
              : view === "map" ? <ReadinessMap graph={graph} selected={selected} onSelect={setSelected} />
              : <ReadinessCards graph={graph} selected={selected} onSelect={setSelected} />}
          </div>
          <DetailDrawer node={node} graph={graph} waiting={waiting} onAct={act} busy={busy}
            onClose={() => setSelected(null)} onSelect={setSelected} />
        </section>
      )}

      <FlowBar journey={journey} waiting={waiting} onAct={act} busy={busy} />

      <div className="grid gap-5 xl:grid-cols-[1fr_400px]">
        <div className="flex flex-col gap-3">
          <PlanningCard journey={journey} />
          <Lanes journey={journey} waiting={waiting} onAct={act} busy={busy} onSelect={(id) => { setSelected(id); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </div>
        <SidePanel journey={journey} onAct={act} busy={busy} canChat={!!waiting} />
      </div>
      <button onClick={onRestart} className="self-start text-[13px] text-muted underline hover:text-ink">{t.app.start.restart}</button>
    </div>
  );
}

export default function Business() {
  const { business, journeys, setJourney } = useDemo();
  const jid = business ? journeys[business.business_id] : null;
  return (
    <AppShell>
      <div className="mx-auto max-w-[1400px] px-4 py-6 md:px-7">
        {!business ? <div className="h-64 animate-pulse rounded-3xl bg-white" />
          : jid ? <Journey key={jid} journeyId={jid} onRestart={() => setJourney(business.business_id, null)} />
          : <StartPanel business={business} onStarted={(d) => setJourney(business.business_id, d.journey.journey_id)} />}
      </div>
    </AppShell>
  );
}
