// Landing: one promise on the left, one picture on the right, then the story, then three doors.
// The page darkens nowhere abruptly: navy hero -> deep-blue story -> a long fade into porcelain.
import { Link } from "react-router-dom";
import Logo from "../components/Logo.jsx";
import LangToggle from "../components/LangToggle.jsx";
import HeroGraphic from "../components/HeroGraphic.jsx";
import Story from "../components/Story.jsx";
import { useLang } from "../lib/i18n.jsx";

function Arrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className="transition-transform group-hover:translate-x-0.5 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" aria-hidden="true">
      <path d="M3 8h9M8.5 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Door({ to, tone, title, body, cta }) {
  const tones = {
    blue: "bg-blue text-white shadow-[0_24px_60px_-24px_rgba(47,91,234,.7)]",
    night: "bg-night text-white shadow-[0_24px_60px_-28px_rgba(7,26,43,.8)]",
    light: "bg-white text-ink border border-line shadow-[0_20px_50px_-30px_rgba(13,27,42,.35)]",
  };
  const sub = { blue: "text-white/80", night: "text-white/70", light: "text-muted" };
  const btn = {
    blue: "bg-white text-blue",
    night: "border border-white/25 text-white",
    light: "border border-line bg-white text-ink",
  };
  return (
    <Link to={to}
      className={`group flex min-h-[250px] flex-col justify-between rounded-[20px] p-8 transition-all duration-300 hover:-translate-y-1.5 ${tones[tone]}`}>
      <div>
        <h3 className="display text-[25px] font-bold">{title}</h3>
        <p className={`mt-3 text-[15px] leading-relaxed ${sub[tone]}`}>{body}</p>
      </div>
      <span className={`mt-8 inline-flex w-fit items-center gap-2 rounded-xl px-5 py-3 text-[15px] font-semibold ${btn[tone]}`}>
        {cta} <Arrow />
      </span>
    </Link>
  );
}

export default function Landing() {
  const { t } = useLang();
  return (
    <div className="min-h-screen bg-night">
      {/* ---------------- hero ---------------- */}
      <section className="relative overflow-hidden text-white">
        <div className="grid-bg pointer-events-none absolute inset-0 [mask-image:linear-gradient(180deg,#000_55%,transparent)]" />
        <div className="pointer-events-none absolute -top-40 h-[640px] w-[900px] rounded-full bg-blue/12 blur-[120px] end-[-200px]" />
        <div className="pointer-events-none absolute bottom-0 h-[380px] w-[520px] rounded-full bg-teal/[.05] blur-[110px] end-[5%]" />

        <nav className="relative mx-auto flex max-w-[1320px] items-center gap-8 px-6 py-6 md:px-10">
          <Logo />
          <div className="hidden items-center gap-7 text-[15px] text-white/70 md:flex">
            <a href="#story" className="hover:text-white">{t.nav.how}</a>
            <Link to="/business" className="hover:text-white">{t.nav.businesses}</Link>
            <Link to="/bank" className="hover:text-white">{t.nav.banks}</Link>
            <Link to="/results" className="hover:text-white">{t.nav.results}</Link>
          </div>
          <div className="flex-1" />
          <LangToggle />
          <Link to="/business" className="hidden rounded-lg bg-blue px-4 py-2 text-[14px] font-semibold hover:bg-blue-2 sm:inline-block">
            {t.nav.demo}
          </Link>
        </nav>

        <div className="relative mx-auto grid max-w-[1320px] items-center gap-10 px-6 pb-24 pt-10 md:px-10 lg:grid-cols-[1.05fr_1fr] lg:pb-32 lg:pt-16">
          <div>
            <h1 className="display text-[44px] font-bold leading-[1.03] sm:text-[60px] lg:text-[72px]">
              {t.hero.title1}<br />{t.hero.title2}
            </h1>
            <p className="mt-6 max-w-[540px] text-[18px] leading-relaxed text-white/72 lg:text-[19px]">{t.hero.body}</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/business" className="group inline-flex items-center gap-2 rounded-xl bg-blue px-5 py-3.5 text-[15px] font-semibold hover:bg-blue-2">
                {t.hero.startBusiness} <Arrow />
              </Link>
              <Link to="/bank" className="inline-flex items-center rounded-xl border border-white/25 px-5 py-3.5 text-[15px] font-semibold hover:bg-white/5">
                {t.hero.openBank}
              </Link>
            </div>
            <p className="mt-12 text-[13.5px] text-white/55">
              {t.hero.made1} <a href="https://www.humain.com" target="_blank" rel="noreferrer" className="font-semibold text-white/85 hover:text-white" dir="ltr">HUMAIN ONE</a> {t.hero.made2}
            </p>
          </div>
          <div className="animate-float mx-auto w-full max-w-[600px]" style={{ animation: "float-y 7s ease-in-out infinite" }}>
            <HeroGraphic />
          </div>
        </div>
      </section>

      {/* ---------------- story ---------------- */}
      <section id="story" className="relative bg-gradient-to-b from-night via-night-2 to-night-2 text-white">
        <div className="mx-auto max-w-[1320px] px-6 pb-20 pt-6 md:px-10">
          <p className="text-[14px] font-semibold text-blue-2">{t.story.kicker}</p>
          <h2 className="display mt-2 text-[32px] font-bold leading-tight sm:text-[40px]">{t.story.title}</h2>
          <div className="mt-10"><Story /></div>
        </div>
      </section>

      {/* ---------------- the fade, then the doors ---------------- */}
      <section className="relative bg-porcelain">
        <div className="h-56 bg-gradient-to-b from-night-2 via-[#3E5B7E] via-45% to-porcelain" aria-hidden="true" />
        <div className="mx-auto -mt-28 grid max-w-[1320px] gap-5 px-6 pb-16 md:px-10 lg:grid-cols-[1.2fr_1fr_1fr]">
          <Door to="/business" tone="blue" {...{ title: t.doors.business.t, body: t.doors.business.d, cta: t.doors.business.cta }} />
          <Door to="/bank" tone="night" {...{ title: t.doors.bank.t, body: t.doors.bank.d, cta: t.doors.bank.cta }} />
          <Door to="/results" tone="light" {...{ title: t.doors.results.t, body: t.doors.results.d, cta: t.doors.results.cta }} />
        </div>
        <footer className="mx-auto flex max-w-[1320px] flex-col gap-4 border-t border-line px-6 py-8 text-[13px] text-muted md:flex-row md:items-center md:justify-between md:px-10">
          <span>{t.foot}</span>
          <Logo size={22} className="text-ink" />
        </footer>
      </section>
    </div>
  );
}
