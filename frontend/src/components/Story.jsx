// "How it works" as a story: five stages, one open at a time. Hover (or tap) opens a stage,
// it lifts and shows a small piece of the real screen; left alone, it plays through by itself.
import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n.jsx";

const AUTOPLAY_MS = 3800;

function Toggle() {
  return (
    <span className="relative inline-block h-5 w-9 flex-none rounded-full bg-teal">
      <span className="absolute top-0.5 h-4 w-4 rounded-full bg-white end-0.5" />
    </span>
  );
}

function Chip({ tone, children }) {
  const tones = {
    teal: "bg-teal/15 text-[#5EE3C9]",
    blue: "bg-blue/25 text-[#AFC2FF]",
    coral: "bg-coral/15 text-[#FF9EA1]",
    amber: "bg-amber/15 text-[#F7C877]",
  };
  return <span className={`rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${tones[tone]}`}>{children}</span>;
}

// A fragment of the product for each stage, so the story shows the thing rather than describing it.
function Vignette({ i, v }) {
  const row = "flex items-center justify-between gap-3 py-2 text-[13px] text-white/85";
  if (i === 0) return (
    <div>
      <div className={row}><span>{v.a}</span><Toggle /></div>
      <div className={`${row} border-t border-line-dark`}><span>{v.b}</span><Toggle /></div>
    </div>
  );
  if (i === 1) return (
    <div>
      {[[v.a, "teal", v.ok], [v.b, "teal", v.ok], [v.c, "blue", v.fetched]].map(([name, tone, label], k) => (
        <div key={k} className={`${row} ${k ? "border-t border-line-dark" : ""}`}>
          <span className="flex items-center gap-2">
            <svg width="14" height="16" viewBox="0 0 14 16" className="flex-none opacity-70"><path d="M1 1h8l4 4v10H1z" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
            {name}
          </span>
          <Chip tone={tone}>{label}</Chip>
        </div>
      ))}
    </div>
  );
  if (i === 2) return (
    <div>
      <div className="py-2 text-[13px] text-[#FF9EA1]">{v.a}</div>
      <div className="border-t border-line-dark py-2 text-[13px] text-[#F7C877]">{v.b}</div>
      <div className="pt-1 text-[12px] text-white/45">{v.ev}</div>
    </div>
  );
  if (i === 3) return (
    <div className="rounded-xl border border-line-dark bg-night/60 p-3">
      <div className="text-[13px] font-semibold text-white">{v.a}</div>
      <div className="mt-3 flex gap-2">
        <span className="rounded-lg bg-blue px-3 py-1.5 text-[12.5px] font-semibold text-white">{v.approve}</span>
        <span className="rounded-lg border border-white/20 px-3 py-1.5 text-[12.5px] text-white/75">{v.later}</span>
      </div>
    </div>
  );
  return (
    <div className="flex flex-col items-start gap-2">
      <span className="inline-flex items-center gap-2 rounded-lg bg-teal/15 px-3 py-2 text-[14px] font-semibold text-[#5EE3C9]">
        <svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {v.a}
      </span>
      <span className="text-[12.5px] text-white/55">{v.b}</span>
    </div>
  );
}

export default function Story() {
  const { t } = useLang();
  const stages = t.story.stages;
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (paused || reduce) return;
    timer.current = setInterval(() => setActive((a) => (a + 1) % stages.length), AUTOPLAY_MS);
    return () => clearInterval(timer.current);
  }, [paused, stages.length]);

  // Cards keep a fixed width (nothing reflows on hover); the open stage's screen shows in
  // one panel underneath, which cross-fades.
  const cur = stages[active];
  return (
    <div onMouseLeave={() => setPaused(false)}>
      <div className="grid gap-3 md:grid-cols-5" onMouseEnter={() => setPaused(true)}>
        {stages.map((s, i) => {
          const on = i === active;
          return (
            <button key={s.t} type="button"
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onClick={() => { setActive(i); setPaused(true); }}
              aria-pressed={on}
              className={`relative flex flex-col overflow-hidden rounded-2xl border p-5 text-start transition-[transform,background-color,border-color,box-shadow] duration-300 ease-out ${
                on ? "-translate-y-1 border-blue/60 bg-night-3/80 shadow-[0_14px_36px_-16px_rgba(47,91,234,.45)]"
                  : "border-line-dark bg-white/[.03] hover:bg-white/[.05]"}`}>
              {/* the timeline: done stages full, the open one filling while it plays */}
              <span className="absolute inset-x-0 top-0 h-[3px] bg-white/5" aria-hidden="true">
                <span key={on && !paused ? `run-${active}` : "still"}
                  className={`absolute inset-y-0 start-0 ${i < active ? "w-full bg-teal/80" : on ? "bg-blue-2" : "w-0"}`}
                  style={on ? (paused ? { width: "100%" } : { animation: `fill-bar ${AUTOPLAY_MS}ms linear forwards` }) : undefined} />
              </span>
              <div className="flex items-center gap-3">
                <span className={`flex h-8 w-8 flex-none items-center justify-center rounded-full text-[14px] font-bold transition-colors duration-300 ${
                  on ? "bg-blue text-white" : "bg-white/8 text-blue-2"}`}>{i + 1}</span>
                <h3 className="text-[17px] font-semibold tracking-tight text-white">{s.t}</h3>
              </div>
              <p className={`mt-3 text-[14px] leading-relaxed transition-colors duration-300 ${on ? "text-white/80" : "text-white/50"}`}>{s.d}</p>
            </button>
          );
        })}
      </div>

      <div className="mt-4 rounded-2xl border border-line-dark bg-night/40 p-5 md:min-h-[150px] md:p-6">
        <div key={active} className="grid items-center gap-5 md:grid-cols-[1fr_minmax(300px,420px)]" style={{ animation: "fade-up .35s ease-out" }}>
          <div>
            <p className="text-[13px] font-semibold text-blue-2">{active + 1} / {stages.length}</p>
            <p className="mt-1 text-[20px] font-semibold text-white">{cur.t}</p>
            <p className="mt-1.5 max-w-[520px] text-[14.5px] leading-relaxed text-white/65">{cur.d}</p>
          </div>
          <div className="rounded-xl border border-line-dark bg-night-2/80 p-4">
            <Vignette i={active} v={cur.v} />
          </div>
        </div>
      </div>
      <p className="mt-4 text-[13px] text-white/40">{t.story.hint}</p>
    </div>
  );
}
