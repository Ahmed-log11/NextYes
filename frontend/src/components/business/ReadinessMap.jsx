// The readiness map: a left-to-right mind map (mirrored in Arabic) from the business to its
// issues, the fixes, and the people or departments handling them. Hover lights up one chain;
// click opens the details.
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLang } from "../../lib/i18n.jsx";
import { EXECUTORS, STATUS, label } from "../../lib/labels.js";
import { connected } from "./graph.js";

const SIZE = { business: [190, 104], issue: [228, 66], fix: [250, 76], who: [176, 60] };
const GAP = 16, PAD = 24, MIN_W = 960;

const EDGE = {
  hard: { stroke: "#E5484D", op: 0.75 }, soft: { stroke: "#F2A93B", op: 0.75 },
  fix: { stroke: "#5B80FF", op: 0.8 }, live: { stroke: "#5B80FF", op: 0.95, dash: true },
  done: { stroke: "#12B39A", op: 0.85 }, off: { stroke: "#6B7F96", op: 0.5, dashed: true },
  plain: { stroke: "#8FA6C4", op: 0.45 },
};

function layout(graph, width, rtl) {
  const cols = [[graph.business], graph.issues, graph.fixes, graph.who];
  const kinds = ["business", "issue", "fix", "who"];
  const heights = cols.map((c, i) => c.length * SIZE[kinds[i]][1] + Math.max(0, c.length - 1) * GAP);
  const H = Math.max(...heights, 240) + PAD * 2;
  const W = Math.max(width, MIN_W);
  const widths = kinds.map((k) => SIZE[k][0]);
  const gap = (W - PAD * 2 - widths.reduce((a, b) => a + b, 0)) / 3;
  const pos = {};
  let x = PAD;
  cols.forEach((col, ci) => {
    const [w, h] = SIZE[kinds[ci]];
    let y = (H - heights[ci]) / 2;
    for (const n of col) {
      pos[n.id] = { x: rtl ? W - x - w : x, y, w, h };
      y += h + GAP;
    }
    x += w + gap;
  });
  return { pos, W, H };
}

function edgePath(a, b, rtl) {
  const x1 = rtl ? a.x : a.x + a.w, y1 = a.y + a.h / 2;
  const x2 = rtl ? b.x + b.w : b.x, y2 = b.y + b.h / 2;
  const dx = (x2 - x1) * 0.5;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

const STATUS_TONE = {
  awaiting_approval: "bg-amber/15 text-[#F7C877]",
  in_progress: "bg-blue/25 text-[#AFC2FF]",
  done: "bg-teal/15 text-[#5EE3C9]",
  declined: "bg-white/8 text-white/50",
  proposed: "bg-white/8 text-white/60",
};

function WhoIcon({ kind }) {
  const paths = {
    agent: <path d="M5 12.5l4 4L19 7" />,
    time: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></>,
    advisor: <><circle cx="12" cy="9" r="3.5" /><path d="M5 20c1.2-3.6 4-5 7-5s5.8 1.4 7 5" /></>,
    team: <><circle cx="9" cy="9" r="3" /><circle cx="16.5" cy="10" r="2.4" /><path d="M3.5 19c.9-3 3-4.5 5.5-4.5s4.6 1.5 5.5 4.5M14.5 15c2.2 0 4.2 1.2 5 4" /></>,
  };
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[kind] ?? paths.team}
    </svg>
  );
}

export function NodeBody({ node, t, lang }) {
  if (node.type === "business") {
    const pct = Math.min(100, node.score);
    return (
      <div className="flex h-full flex-col justify-center px-4">
        <div className="truncate text-[14px] font-semibold text-white">{node.title}</div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="display text-[30px] font-bold text-white">{Math.round(node.score)}</span>
          <span className="text-[12.5px] text-white/50">/ {node.threshold} {t.app.band.needs}</span>
        </div>
        <div className="relative mt-1.5 h-1.5 rounded-full bg-white/10">
          <span className={`absolute inset-y-0 start-0 rounded-full ${node.score >= node.threshold ? "bg-teal" : "bg-amber"}`} style={{ width: `${pct}%` }} />
          <span className="absolute -top-1 h-3.5 w-0.5 bg-white/80" style={{ insetInlineStart: `${node.threshold}%` }} />
        </div>
      </div>
    );
  }
  if (node.type === "issue") {
    const tone = node.resolved ? "border-teal text-[#5EE3C9]" : node.severity === "hard" ? "border-coral text-[#FF9EA1]" : "border-amber text-[#F7C877]";
    return (
      <div className={`flex h-full flex-col justify-center border-s-[3px] px-3.5 ${tone}`}>
        <div className={`truncate text-[13.5px] font-semibold ${node.resolved ? "line-through decoration-teal/60" : ""}`}>{node.title}</div>
        <div className="mt-0.5 text-[11.5px] text-white/50">
          {node.resolved ? `✓ ${lang === "ar" ? "تم حلها" : "Resolved"}` : node.unfixable ? t.app.map.unfixable : node.severity === "hard" ? (lang === "ar" ? "لازم تتعالج" : "Must be fixed") : (lang === "ar" ? "تخفض الدرجة" : "Lowers the score")}
        </div>
      </div>
    );
  }
  if (node.type === "fix") {
    return (
      <div className="flex h-full flex-col justify-center px-3.5">
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-white">{node.title}</div>
        <div className="mt-1.5 flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-semibold ${STATUS_TONE[node.status]}`}>{label(STATUS, node.status, lang)}</span>
          <span className="truncate text-[11px] text-white/45">{label(EXECUTORS, node.executor, lang)}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-full items-center gap-2.5 px-3">
      <span className={`flex h-8 w-8 flex-none items-center justify-center rounded-lg ${
        node.kind === "agent" ? "bg-blue/30 text-[#AFC2FF]" : node.kind === "advisor" ? "bg-coral/20 text-[#FF9EA1]" : "bg-white/8 text-white/80"}`}>
        <WhoIcon kind={node.kind} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold text-white">{node.title}</span>
        <span className="block truncate text-[11px] text-white/50">
          {node.people.length ? node.people.join(", ") : node.suggested ? t.app.map.suggested : ""}
        </span>
      </span>
    </div>
  );
}

export default function ReadinessMap({ graph, selected, onSelect }) {
  const { t, lang, rtl } = useLang();
  const wrap = useRef(null);
  const [width, setWidth] = useState(1100);
  const [hover, setHover] = useState(null);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { pos, W, H } = useMemo(() => layout(graph, width, rtl), [graph, width, rtl]);
  const lit = useMemo(() => connected(graph, hover ?? selected), [graph, hover, selected]);
  const nodes = [graph.business, ...graph.issues, ...graph.fixes, ...graph.who];
  const kindsHead = [["issue", 1], ["fix", 2], ["who", 3]];

  return (
    <div ref={wrap} className="overflow-x-auto">
      <div className="relative" style={{ width: W, height: H + 28 }}>
        {/* column captions */}
        {kindsHead.map(([k, ci]) => {
          const col = ci === 1 ? graph.issues : ci === 2 ? graph.fixes : graph.who;
          const p = col[0] && pos[col[0].id];
          return p ? (
            <div key={k} className="absolute top-0 text-[12px] font-semibold text-white/45" style={{ left: p.x, width: p.w }}>
              {t.app.map.cols[k]}
            </div>
          ) : null;
        })}
        <div className="absolute inset-x-0 bottom-0" style={{ top: 28 }}>
          <svg className="absolute inset-0" width={W} height={H} aria-hidden="true">
            {graph.edges.map((e, i) => {
              const a = pos[e.from], b = pos[e.to];
              if (!a || !b) return null;
              const st = EDGE[e.tone] ?? EDGE.plain;
              const on = !lit || (lit.has(e.from) && lit.has(e.to));
              return (
                <g key={i} style={{ opacity: on ? 1 : 0.12, transition: "opacity .25s" }}>
                  <path d={edgePath(a, b, rtl)} fill="none" stroke={st.stroke} strokeOpacity={st.op} strokeWidth={on && lit ? 2.4 : 1.6}
                    strokeDasharray={st.dashed ? "5 5" : undefined} />
                  {st.dash && <path d={edgePath(a, b, rtl)} fill="none" stroke="#fff" strokeOpacity=".7" strokeWidth="1.3" className="flow-dash" />}
                </g>
              );
            })}
          </svg>
          {nodes.map((n) => {
            const p = pos[n.id];
            const on = !lit || lit.has(n.id);
            const isSel = selected === n.id;
            return (
              <button key={n.id} type="button"
                onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                onClick={() => onSelect(isSel ? null : n.id)}
                className={`absolute overflow-hidden rounded-xl border text-start backdrop-blur transition-all duration-200 ${
                  isSel ? "border-blue-2 bg-night-3 shadow-[0_0_0_3px_rgba(91,128,255,.25),0_12px_30px_-10px_rgba(47,91,234,.7)]"
                    : n.type === "business" ? "border-blue/50 bg-night-3/95 hover:border-blue-2"
                    : "border-line-dark bg-night-2/90 hover:-translate-y-0.5 hover:border-blue-2/70"}`}
                style={{ left: p.x, top: p.y, width: p.w, height: p.h, opacity: on ? 1 : 0.28 }}>
                <NodeBody node={n} t={t} lang={lang} />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
