// Results dashboard. Every number is computed here from the evaluation reports the server
// holds (backend/reports, real model runs on the dev split), nothing is typed in by hand.
import { useEffect, useMemo, useState } from "react";
import AppShell from "../components/AppShell.jsx";
import { useLang } from "../lib/i18n.jsx";
import { api } from "../lib/api.js";

const LEVELS = ["clean", "realistic", "hard"];
const LENDER = "commercial_bank_sme";
const pct = (x) => `${(x * 100).toFixed(x >= 0.995 && x < 1 ? 1 : 0)}%`;

function summarise(reports) {
  const rows = LEVELS.map((lv) => reports.find((r) => r.split === "dev" && r.reader === "haiku" && r.level === lv)).filter(Boolean);
  if (!rows.length) return null;
  const per = rows.map((r) => {
    const s = r.summary;
    const [agree, n] = s.verdict_agreement?.[LENDER] ?? [0, 0];
    return {
      level: r.level, businesses: s.businesses, decided: n, wrong: Math.round(n - agree * n),
      figures: s.field_accuracy_overall?.[0] ?? 0, abstained: s.abstained ?? s.businesses - n,
      missing: s.missing_documents_exact ?? [0, 0], requested: s.completed_after_request ?? 0,
      conflicts: s.conflict_recall ?? [null, 0], falseAlarms: s.conflict_false_alarms ?? 0,
      planted: s.injections_planted ?? 0, flagged: s.injections_flagged ?? 0, resisted: s.injections_resisted ?? 0,
    };
  });
  const sum = (k) => per.reduce((a, r) => a + r[k], 0);
  return {
    per, journeys: sum("businesses"), wrong: sum("wrong"), abstained: sum("abstained"),
    missingFound: per.reduce((a, r) => a + Math.round(r.missing[0] * r.missing[1]), 0), missingN: per.reduce((a, r) => a + r.missing[1], 0),
    requested: sum("requested"),
    conflictsFound: per.reduce((a, r) => a + Math.round((r.conflicts[0] ?? 0) * r.conflicts[1]), 0), conflictsN: per.reduce((a, r) => a + r.conflicts[1], 0),
    falseAlarms: sum("falseAlarms"), planted: sum("planted"), flagged: sum("flagged"), resisted: sum("resisted"),
  };
}

function Tile({ big, of, title, sub }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5 transition-transform hover:-translate-y-0.5">
      <p className="display text-[36px] font-bold leading-none">{big}<span className="text-[18px] text-muted"> / {of}</span></p>
      <p className="mt-2 text-[14.5px] font-semibold">{title}</p>
      <p className="mt-1 text-[12.5px] text-muted">{sub}</p>
    </div>
  );
}

export default function Results() {
  const { t } = useLang();
  const R = t.app.results;
  const [reports, setReports] = useState(null);
  const [planner, setPlanner] = useState(null);
  useEffect(() => { api.evaluation().then(setReports).catch(() => setReports([])); }, []);
  useEffect(() => { api.plannerEvaluation().then(setPlanner).catch(() => setPlanner([])); }, []);
  const s = useMemo(() => (reports ? summarise(reports) : null), [reports]);

  return (
    <AppShell switcher={false}>
      <div className="mx-auto max-w-[1300px] px-4 py-6 md:px-7">
        <h1 className="display text-[30px] font-bold">{R.title}</h1>
        <p className="mt-2 max-w-[760px] text-[15px] leading-relaxed text-muted">{R.sub}</p>

        {reports && !s && <p className="mt-6 rounded-xl bg-porcelain p-4 text-muted">{R.noData}</p>}
        {!reports && <div className="mt-6 h-56 animate-pulse rounded-3xl bg-white" />}
        {s && (
          <>
            <div className="mt-6 grid gap-5 lg:grid-cols-[1.1fr_1fr]">
              <div className="relative overflow-hidden rounded-3xl bg-night p-7 text-white">
                <div className="grid-bg pointer-events-none absolute inset-0 opacity-50" />
                <div className="pointer-events-none absolute -bottom-24 h-64 w-[480px] rounded-full bg-teal/25 blur-[90px] end-0" />
                <div className="relative">
                  <p className="display text-[96px] font-bold leading-none text-[#5EE3C9]">{s.wrong}</p>
                  <p className="mt-2 text-[20px] font-semibold">{R.wrong} <span className="text-white/55">· {s.journeys} {R.journeys}</span></p>
                  <p className="mt-5 max-w-[460px] text-[14.5px] leading-relaxed text-white/70">
                    <b className="text-white">{s.abstained}</b> {R.abstained}.
                  </p>
                </div>
              </div>
              <div className="rounded-3xl border border-line bg-white p-6">
                <h2 className="text-[16px] font-semibold">{R.byLevel}</h2>
                <div className="mt-4 grid grid-cols-[1fr_repeat(3,auto)] gap-x-5 gap-y-3 text-[13.5px]">
                  <span className="text-muted">{R.level}</span><span className="text-muted">{R.figures}</span><span className="text-muted">{R.decisions}</span><span className="text-muted">{R.stopped}</span>
                  {s.per.map((r) => (
                    <div key={r.level} className="contents">
                      <span className="font-semibold">{t.app.start.levels[r.level]}</span>
                      <span className="flex items-center gap-2">
                        <span className="h-1.5 w-20 overflow-hidden rounded-full bg-porcelain"><span className="block h-full rounded-full bg-blue" style={{ width: `${r.figures * 100}%` }} /></span>
                        {pct(r.figures)}
                      </span>
                      <span>{r.decided - r.wrong} / {r.decided}</span>
                      <span>{r.abstained}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <h2 className="mt-8 text-[16px] font-semibold">{R.tasks}</h2>
            <div className="mt-3 grid gap-4 md:grid-cols-3">
              <Tile big={s.missingFound} of={s.missingN} title={R.missing} sub={`${s.requested} ${R.missingS}`} />
              <Tile big={s.conflictsFound} of={s.conflictsN} title={R.conflicts} sub={`${s.falseAlarms} ${R.conflictsS}`} />
              <Tile big={s.resisted} of={s.planted} title={R.injections} sub={`${s.flagged} ${R.injectionsS}`} />
            </div>

            <PlannerSection reports={planner} />

            <div className="mt-8 rounded-3xl border border-line bg-white p-6">
              <h2 className="text-[16px] font-semibold">{R.changed}</h2>
              <div className="mt-3">
                {R.CHANGES.map(([what, why]) => (
                  <div key={what} className="grid gap-1 border-t border-line py-3 first:border-0 md:grid-cols-[280px_1fr] md:gap-6">
                    <span className="text-[14px] font-semibold">{what}</span><span className="text-[13.5px] text-muted">{why}</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="mt-4 text-[12.5px] text-muted">{R.note}</p>
          </>
        )}
      </div>
    </AppShell>
  );
}

function PlannerSection({ reports }) {
  const { t } = useLang();
  const P = t.app.results.planner;
  const rep = reports?.find((r) => r.split === "dev" && r.brain === "claude");
  if (!reports) return null;
  if (!rep) return <p className="mt-8 rounded-2xl bg-porcelain p-4 text-[13.5px] text-muted">{P.none}</p>;
  const s = rep.summary;
  const rows = [["approve_all", P.approveAll], ["decline_one", P.declineOne]];
  const rounds = s.approve_all.agent_rounds.compared + s.decline_one.agent_rounds.compared;
  const valid = s.approve_all.agent_rounds.valid_first_try + s.decline_one.agent_rounds.valid_first_try;
  const declinedRules = s.decline_one.rules.journeys - s.decline_one.rules.ready;
  const rescued = s.decline_one.agent.ready - s.decline_one.rules.ready;
  return (
    <div className="mt-8 rounded-3xl border border-line bg-white p-6">
      <h2 className="text-[16px] font-semibold">{P.title}</h2>
      <p className="mt-1 max-w-[860px] text-[13.5px] leading-relaxed text-muted">{P.sub}</p>
      <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="grid grid-cols-[1fr_repeat(2,auto)] items-center gap-x-6 gap-y-3 text-[13.5px]">
          <span /><span className="font-semibold text-muted">{P.rules}</span><span className="font-semibold text-blue">{P.agent}</span>
          {rows.map(([k, label]) => (
            <div key={k} className="contents">
              <span className="col-span-3 mt-2 border-t border-line pt-3 text-[13px] font-semibold">{label}</span>
              <span className="text-muted">{P.ready}</span>
              <span>{s[k].rules.ready} / {s[k].rules.journeys}</span>
              <span className="font-semibold text-blue">{s[k].agent.ready} / {s[k].agent.journeys}</span>
              <span className="text-muted">{P.ownerSteps}</span>
              <span>{s[k].rules.mean_owner_steps}</span>
              <span className="font-semibold text-blue">{s[k].agent.mean_owner_steps}</span>
            </div>
          ))}
        </div>
        <div className="grid gap-3">
          <Tile big={valid} of={rounds} title={P.valid} sub="validate_plan" />
          <Tile big={rescued} of={declinedRules} title={P.rescued} sub={P.rescuedNote} />
        </div>
      </div>
    </div>
  );
}
