// Chat with the agent, the timeline (the audit log as the owner sees it) and the documents.
import { useEffect, useRef, useState } from "react";
import { useLang } from "../../lib/i18n.jsx";
import { api } from "../../lib/api.js";
import { DOCS, label } from "../../lib/labels.js";

const ACTOR_DOT = { agent: "bg-blue", owner: "bg-amber", lender: "bg-teal", system: "bg-muted" };

function Chat({ journey, onAct, busy, canChat }) {
  const { t, lang } = useLang();
  const [text, setText] = useState("");
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [journey.messages.length]);
  const send = async (e) => {
    e.preventDefault();
    const v = text.trim();
    if (!v) return;
    setText("");
    await onAct({ type: "chat", text: v });
  };
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-2.5 overflow-y-auto pe-1">
        {journey.messages.map((m, i) => (
          <div key={i} dir="auto"
            className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed ${
              m.role === "owner" ? "ms-auto rounded-ee-sm bg-blue text-white"
                : m.refused ? "rounded-es-sm border border-coral/30 bg-coral-soft/60" : "rounded-es-sm bg-porcelain"}`}>
            {m.refused && <span className="mb-1 block text-[11px] font-semibold text-[#B4282D]">{t.app.side.refused}</span>}
            {m.text}
          </div>
        ))}
        {busy === "chat" && <div className="w-16 animate-pulse rounded-2xl bg-porcelain px-3.5 py-2.5 text-[13.5px]">…</div>}
        <div ref={end} />
      </div>
      <form onSubmit={send} className="mt-3 flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} disabled={!canChat}
          placeholder={t.app.side.placeholder} dir="auto"
          className="min-w-0 flex-1 rounded-xl border border-line px-3.5 py-2.5 text-[14px] focus:border-blue focus:outline-none disabled:bg-porcelain" />
        <button disabled={!canChat || !text.trim() || !!busy} className="rounded-xl bg-ink px-4 text-[14px] font-semibold text-white disabled:opacity-40">{t.app.side.send}</button>
      </form>
      <p className="mt-2 text-[11.5px] text-muted">{lang === "ar" ? "جرّب: «أقدر أخفي قرضي عن البنك؟»" : "Try: “can you hide my loan from the bank?”"}</p>
    </div>
  );
}

function Timeline({ journey }) {
  const { lang } = useLang();
  return (
    <ol className="space-y-0 overflow-y-auto">
      {[...journey.events].reverse().map((e) => (
        <li key={e.seq} className="grid grid-cols-[14px_1fr] gap-3 border-t border-line py-2.5 first:border-0">
          <span className={`mt-1.5 h-2 w-2 rounded-full ${ACTOR_DOT[e.actor] ?? "bg-muted"}`} />
          <span>
            <span className="block text-[13px] leading-snug">{e.text[lang] ?? e.text.en}</span>
            <span className="text-[11.5px] text-muted">{lang === "ar" ? "الشهر" : "Month"} {e.month} · {e.kind}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function Documents({ journey }) {
  const { t, lang } = useLang();
  const [names, setNames] = useState(null);
  useEffect(() => { api.documents?.(journey.journey_id).then(setNames).catch(() => setNames([])); }, [journey.journey_id, journey.fetched_documents.length]);
  return (
    <ul className="space-y-1.5">
      {(names ?? []).map((n) => (
        <li key={n}>
          <a href={api.documentUrl(journey.journey_id, n)} target="_blank" rel="noreferrer"
            className="flex items-center justify-between gap-3 rounded-xl border border-line px-3.5 py-2.5 text-[13.5px] hover:border-blue">
            <span className="flex items-center gap-2.5">
              <svg width="14" height="16" viewBox="0 0 14 16" className="text-muted"><path d="M1 1h8l4 4v10H1z" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
              {label(DOCS, n, lang)}
            </span>
            {journey.fetched_documents.includes(n) && <span className="rounded-md bg-blue-soft px-2 py-0.5 text-[11px] font-semibold text-[#2443B8]">{t.app.side.fetched}</span>}
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function SidePanel({ journey, onAct, busy, canChat }) {
  const { t } = useLang();
  const [tab, setTab] = useState("chat");
  const tabs = [["chat", t.app.side.chat], ["timeline", t.app.side.timeline], ["documents", t.app.side.documents]];
  return (
    <div className="flex h-[620px] flex-col rounded-2xl border border-line bg-white p-4">
      <div className="mb-3 flex gap-1 rounded-xl bg-porcelain p-1">
        {tabs.map(([k, v]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex-1 rounded-lg px-2 py-1.5 text-[13px] font-semibold transition-colors ${tab === k ? "bg-white shadow-sm" : "text-muted hover:text-ink"}`}>{v}</button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "chat" && <Chat journey={journey} onAct={onAct} busy={busy} canChat={canChat} />}
        {tab === "timeline" && <Timeline journey={journey} />}
        {tab === "documents" && <Documents journey={journey} />}
      </div>
    </div>
  );
}
