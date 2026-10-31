import { useLang } from "../lib/i18n.jsx";

export default function LangToggle({ dark = true }) {
  const { lang, setLang } = useLang();
  const base = dark ? "border-white/20 text-white/60" : "border-line text-muted";
  const on = dark ? "bg-white/12 text-white" : "bg-ink text-white";
  return (
    <div className={`flex overflow-hidden rounded-lg border text-[13px] ${base}`} role="group" aria-label="Language">
      {[["en", "EN"], ["ar", "عربي"]].map(([code, label]) => (
        <button key={code} onClick={() => setLang(code)}
          className={`px-3 py-1.5 transition-colors ${lang === code ? on : "hover:text-current"}`}
          aria-pressed={lang === code}>
          {label}
        </button>
      ))}
    </div>
  );
}
