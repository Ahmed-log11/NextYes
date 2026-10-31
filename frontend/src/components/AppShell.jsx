// The frame around the app screens: a slim navy rail and a top bar with the business
// switcher, so a judge can jump between demo businesses from any screen.
import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import Logo from "./Logo.jsx";
import LangToggle from "./LangToggle.jsx";
import { useLang, pick } from "../lib/i18n.jsx";
import { useDemo } from "../lib/store.jsx";
import { STAGES, label, sar } from "../lib/labels.js";

const ICONS = {
  business: <path d="M4 20V8l8-4 8 4v12M9 20v-6h6v6M4 20h16" />,
  bank: <path d="M3 9l9-5 9 5M5 10v8M10 10v8M14 10v8M19 10v8M3 20h18" />,
  results: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
};

function RailItem({ to, icon, text }) {
  return (
    <NavLink to={to}
      className={({ isActive }) => `flex h-14 w-14 flex-col items-center justify-center gap-1 rounded-xl text-[10.5px] transition-colors ${
        isActive ? "bg-night-3 text-white" : "text-white/55 hover:bg-white/5 hover:text-white"}`}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{ICONS[icon]}</svg>
      {text}
    </NavLink>
  );
}

function BusinessSwitcher() {
  const { lang, t } = useLang();
  const { businesses, business, setSelected, journeys } = useDemo();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!business) return <div className="h-10 w-64 animate-pulse rounded-xl bg-porcelain" />;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex items-center gap-3 rounded-xl border border-line px-3 py-2 text-start hover:border-blue/50">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-soft text-[13px] font-bold text-blue">
          {business.name.en.trim()[0]}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[14.5px] font-semibold">{pick(business.name, lang)}</span>
          <span className="block truncate text-[12px] text-muted">
            {pick(business.sector, lang)} · {pick(business.city, lang)} · {sar(business.request.amount_sar, lang)} {t.app.bar.requested}
          </span>
        </span>
        <svg width="14" height="14" viewBox="0 0 16 16" className="ms-2 text-muted"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>
      </button>
      {open && (
        <div className="absolute z-30 mt-2 w-[min(420px,90vw)] overflow-hidden rounded-2xl border border-line bg-white shadow-xl">
          <p className="px-4 pt-3 text-[12px] font-semibold text-muted">{t.app.bar.switch}</p>
          {businesses.map((b) => (
            <button key={b.business_id} onClick={() => { setSelected(b.business_id); setOpen(false); }}
              className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-start hover:bg-porcelain ${
                b.business_id === business.business_id ? "bg-blue-soft/50" : ""}`}>
              <span className="min-w-0">
                <span className="block truncate text-[14px] font-semibold">{pick(b.name, lang)}</span>
                <span className="block truncate text-[12px] text-muted">{pick(b.sector, lang)} · {sar(b.request.amount_sar, lang)}</span>
              </span>
              {journeys[b.business_id] && <span className="flex-none rounded-md bg-teal-soft px-2 py-0.5 text-[11px] font-semibold text-[#0B7A68]">●</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AppShell({ children, switcher = true }) {
  const { t } = useLang();
  const { apiError } = useDemo();
  return (
    <div className="flex min-h-screen bg-porcelain">
      <aside className="sticky top-0 hidden h-screen w-[84px] flex-none flex-col items-center gap-2 bg-night py-4 md:flex">
        <Link to="/" title={t.app.rail.home} className="mb-4"><Logo word={false} size={36} /></Link>
        <RailItem to="/business" icon="business" text={t.app.rail.business} />
        <RailItem to="/bank" icon="bank" text={t.app.rail.bank} />
        <RailItem to="/results" icon="results" text={t.app.rail.results} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-[68px] items-center gap-4 border-b border-line bg-white/90 px-4 backdrop-blur md:px-7">
          <Link to="/" className="md:hidden"><Logo word={false} size={30} /></Link>
          {switcher && <BusinessSwitcher />}
          <div className="flex-1" />
          <nav className="flex gap-1 md:hidden">
            {["business", "bank", "results"].map((k) => (
              <NavLink key={k} to={`/${k}`} className={({ isActive }) => `rounded-lg px-2 py-1 text-[13px] ${isActive ? "bg-ink text-white" : "text-muted"}`}>{t.app.rail[k]}</NavLink>
            ))}
          </nav>
          <LangToggle dark={false} />
        </header>
        {apiError && (
          <div className="mx-4 mt-4 rounded-xl border border-coral/30 bg-coral-soft px-4 py-3 text-[14px] text-[#B4282D] md:mx-7">
            <b>{t.app.errors.api}</b> ({apiError}). {t.app.errors.apiHint}
          </div>
        )}
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}

export const stageLabel = (stage, lang) => label(STAGES, stage, lang);
