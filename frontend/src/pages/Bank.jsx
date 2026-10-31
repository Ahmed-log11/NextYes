// The lender's credit desk: files owners chose to submit, the decision, the rules behind it,
// how the documents were checked, and the full audit log. A file is empty until submission.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell.jsx";
import { useLang, pick } from "../lib/i18n.jsx";
import { useDemo } from "../lib/store.jsx";
import { api } from "../lib/api.js";
import { BLOCKERS, DOCS, RULES, STAGES, label, sar } from "../lib/labels.js";

const ACTOR_DOT = { agent: "bg-blue", owner: "bg-amber", lender: "bg-teal", system: "bg-muted" };

function useFiles(journeys) {
  const [files, setFiles] = useState({});
  useEffect(() => {
    let live = true;
    Object.entries(journeys).forEach(([bid, jid]) => {
      Promise.all([api.bank(jid), api.journey(jid)])
        .then(([bank, j]) => live && setFiles((f) => ({ ...f, [jid]: { bid, jid, bank, journey: j.journey } })))
        .catch(() => {});
    });
    return () => { live = false; };
  }, [journeys]);
  return files;
}

export default function Bank() {
  const { t, lang } = useLang();
  const B = t.app.bank;
  const { journeys } = useDemo();
  const files = useFiles(journeys);
  const [policies, setPolicies] = useState([]);
  useEffect(() => { api.policies().then(setPolicies).catch(() => {}); }, []);
  const list = useMemo(() => Object.values(files).sort((a, b) => Number(b.bank.submitted) - Number(a.bank.submitted)), [files]);
  const [sel, setSel] = useState(null);
  const current = files[sel] ?? list.find((f) => f.bank.submitted) ?? null;

  return (
    <AppShell switcher={false}>
      <div className="grid min-h-[calc(100vh-68px)] lg:grid-cols-[340px_1fr]">
        {/* inbox */}
        <aside className="border-e border-line bg-white p-5">
          <h1 className="display text-[22px] font-bold">{B.title}</h1>
          <p className="mt-1 text-[13px] text-muted">{B.inboxHint}</p>
          <p className="mt-5 text-[12.5px] font-semibold text-muted">{B.inbox}</p>
          {!list.length && (
            <div className="mt-3 rounded-2xl bg-porcelain p-4 text-[14px] text-muted">
              {B.none}
              <Link to="/business" className="mt-3 block w-fit rounded-lg bg-blue px-3.5 py-2 text-[13.5px] font-semibold text-white">{B.run}</Link>
            </div>
          )}
          <div className="mt-2 space-y-2">
            {list.map((f) => {
              const d = f.bank.decisions.at(-1);
              const on = current?.jid === f.jid;
              return (
                <button key={f.jid} disabled={!f.bank.submitted} onClick={() => setSel(f.jid)}
                  className={`w-full rounded-xl border p-3.5 text-start transition-all ${on ? "border-blue shadow-[0_0_0_3px_var(--color-blue-soft)]" : "border-line hover:border-blue/40"} disabled:cursor-default disabled:opacity-60`}>
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-[14.5px] font-semibold">{pick(f.bank.business.name, lang)}</span>
                    {d ? <span className={`flex-none rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${d.approved ? "bg-teal-soft text-[#0B7A68]" : "bg-coral-soft text-[#B4282D]"}`}>{d.approved ? B.approved : B.declined}</span>
                      : <span className="flex-none rounded-md bg-porcelain px-2 py-0.5 text-[11.5px] text-muted">{B.notSubmitted}</span>}
                  </span>
                  <span className="mt-1 block truncate text-[12.5px] text-muted">
                    {f.bank.submitted ? `${sar(f.bank.application.request.amount_sar, lang)} · ${f.bank.application.request.tenor_months} ${B.months}` : label(STAGES, f.journey.stage, lang)}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        {/* the file */}
        <section className="p-5 md:p-7">
          {current ? <File f={current} policy={policies.find((p) => p.policy_id === current.bank.lender)} /> : (
            <div className="grid h-full place-items-center text-center text-muted"><p className="max-w-[360px] text-[15px]">{B.none}</p></div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function File({ f, policy }) {
  const { t, lang } = useLang();
  const B = t.app.bank;
  const { bank, journey } = f;
  const d = bank.decisions.at(-1);
  const app = bank.application;
  const failed = new Set(d?.reasons?.map((r) => r.code ?? r) ?? []);
  const flags = [...(bank.flags.conflicts ?? []), ...(bank.flags.document_instructions ?? [])];

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <div className={`relative overflow-hidden rounded-3xl bg-night p-6 text-white xl:col-span-2 md:p-7`}>
        <div className={`pointer-events-none absolute -top-24 h-64 w-[520px] rounded-full blur-[90px] start-0 ${d?.approved ? "bg-teal/30" : "bg-coral/25"}`} />
        <div className="relative grid gap-6 md:grid-cols-[1.4fr_repeat(4,1fr)] md:items-end">
          <div>
            <p className="text-[13px] text-white/55">{pick(bank.business.name, lang)} · {pick(bank.business.sector, lang)}</p>
            <p className={`display mt-1 text-[34px] font-bold ${d?.approved ? "text-[#5EE3C9]" : "text-[#FF9EA1]"}`}>{d?.approved ? B.approved : B.declined}</p>
            <p className="text-[12.5px] text-white/50">{B.byEngine}</p>
          </div>
          {[[B.amount, sar(app.request.amount_sar, lang)], [B.tenor, `${app.request.tenor_months} ${B.months}`],
            [B.score, `${Math.round(app.score)} / ${app.threshold}`], [B.month, d?.month ?? app.prepared_month]].map(([k, v]) => (
            <div key={k}><p className="text-[12.5px] text-white/50">{k}</p><p className="display mt-1 text-[21px] font-bold">{v}</p></div>
          ))}
        </div>
        {d && !d.approved && d.reasons?.length > 0 && (
          <p className="relative mt-4 text-[13.5px] text-white/75">{B.reasons}: {d.reasons.map((r) => label(BLOCKERS, r.code ?? r, lang)).join(" · ")}</p>
        )}
      </div>

      <div className="rounded-2xl border border-line bg-white p-5">
        <h3 className="text-[15px] font-semibold">{B.rules} <span className="text-muted">· {pick(policy?.name, lang)}</span></h3>
        <div className="mt-3">
          {(policy?.rules ?? []).map((r) => {
            const bad = failed.has(r.id);
            return (
              <div key={r.id} className="grid grid-cols-[18px_1fr_auto] items-start gap-3 border-t border-line py-2.5 first:border-0">
                <span className={`mt-1 h-2.5 w-2.5 rounded-full ${bad ? "bg-coral" : "bg-teal"}`} />
                <span className="min-w-0">
                  <span className="block text-[13.5px] font-medium">{label(RULES, r.id, lang)}</span>
                  <a href={r.source_url} target="_blank" rel="noreferrer" className="block truncate text-[12px] text-muted hover:text-blue" dir="ltr">{r.source}</a>
                </span>
                <span className="flex flex-col items-end gap-1">
                  <span className={`text-[12px] font-semibold ${bad ? "text-[#B4282D]" : "text-[#0B7A68]"}`}>{bad ? B.failed : B.passed}</span>
                  {r.assumption && <span className="rounded bg-amber-soft px-1.5 py-0.5 text-[10.5px] font-semibold text-[#9A6411]">{B.ours}</span>}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-5">
        <div className="rounded-2xl border border-line bg-white p-5">
          <h3 className="text-[15px] font-semibold">{B.checks}</h3>
          {journey.extraction_checks.map((c) => (
            <div key={c.name} className="grid grid-cols-[18px_1fr] gap-3 border-t border-line py-2.5 first:border-0">
              <span className={`mt-1 h-2.5 w-2.5 rounded-full ${c.passed ? "bg-teal" : "bg-amber"}`} />
              <span>
                <span className="block text-[13.5px] font-medium">{B.CHECKS[c.name] ?? c.name}</span>
                <span className="block text-[12px] text-muted" dir="ltr">{c.detail}</span>
              </span>
            </div>
          ))}
          {journey.fetched_documents.length > 0 && (
            <p className="mt-2 rounded-lg bg-blue-soft px-3 py-2 text-[12.5px] text-[#2443B8]">
              {lang === "ar" ? "جلبه الوكيل من مصدره: " : "Fetched by the agent from its source: "}{journey.fetched_documents.map((n) => label(DOCS, n, lang)).join(", ")}
            </p>
          )}
        </div>
        <div className="rounded-2xl border border-line bg-white p-5">
          <h3 className="text-[15px] font-semibold">{B.flags}</h3>
          {flags.length ? flags.map((x, i) => (
            <p key={i} className="mt-2 rounded-lg bg-amber-soft px-3 py-2 text-[12.5px] text-[#9A6411]" dir="ltr">{x.text ?? x.detail ?? JSON.stringify(x)}</p>
          )) : <p className="mt-2 text-[13.5px] text-muted">{B.noFlags}</p>}
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-white p-5 xl:col-span-2">
        <h3 className="text-[15px] font-semibold">{B.log} <span className="text-muted">· {bank.audit_log.length} {B.entries}</span></h3>
        <ol className="mt-2 max-h-[420px] overflow-y-auto">
          {bank.audit_log.map((e) => (
            <li key={e.seq} className="grid grid-cols-[46px_14px_1fr_auto] items-start gap-3 border-t border-line py-2 text-[13px] first:border-0">
              <span className="text-muted">#{e.seq}</span>
              <span className={`mt-1.5 h-2 w-2 rounded-full ${ACTOR_DOT[e.actor]}`} />
              <span>{e.text[lang] ?? e.text.en}</span>
              <span className="font-mono text-[11.5px] text-muted">{e.kind}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
