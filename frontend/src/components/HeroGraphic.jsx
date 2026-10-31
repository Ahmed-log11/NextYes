// The hero picture: one path from "declined" to "approved" through the four things the agent
// does. No numbers here on purpose; the numbers live on the journey screen.
import { useLang } from "../lib/i18n.jsx";

const W = 600;
const POINTS = [
  { key: "no", x: 70, y: 300 },
  { key: "read", x: 178, y: 160 },
  { key: "diagnose", x: 272, y: 336 },
  { key: "fix", x: 364, y: 170 },
  { key: "apply", x: 444, y: 334 },
  { key: "yes", x: 536, y: 214 },
];

function curve(pts) {
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    const dx = (b.x - a.x) * 0.55;
    d += ` C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
  }
  return d;
}

export default function HeroGraphic() {
  const { t, rtl } = useLang();
  const pts = POINTS.map((p) => ({ ...p, x: rtl ? W - p.x : p.x }));
  const d = curve(pts);
  const yes = pts[pts.length - 1];
  const no = pts[0];

  return (
    <svg viewBox="-40 0 680 480" className="w-full h-auto" role="img"
      aria-label={`${t.hero.g.no} → ${t.hero.g.yes}`}>
      <defs>
        <radialGradient id="hg-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#2F5BEA" stopOpacity=".12" />
          <stop offset="1" stopColor="#2F5BEA" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="hg-yes" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#12B39A" stopOpacity=".12" />
          <stop offset="1" stopColor="#12B39A" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="hg-line" x1={rtl ? "1" : "0"} y1="0" x2={rtl ? "0" : "1"} y2="0">
          <stop offset="0" stopColor="#C8676B" />
          <stop offset=".25" stopColor="#6F88C9" />
          <stop offset=".8" stopColor="#6F88C9" />
          <stop offset="1" stopColor="#3FA593" />
        </linearGradient>
        <filter id="hg-blur"><feGaussianBlur stdDeviation="6" /></filter>
      </defs>

      <ellipse cx="300" cy="250" rx="360" ry="240" fill="url(#hg-glow)" />
      <circle cx={yes.x} cy={yes.y} r="110" fill="url(#hg-yes)" />

      {/* orbit rings around the yes */}
      {[70, 96, 124].map((r, i) => (
        <circle key={r} cx={yes.x} cy={yes.y} r={r} fill="none" stroke="#5B80FF"
          strokeOpacity={0.12 - i * 0.03} strokeDasharray={i === 1 ? "2 6" : undefined} />
      ))}

      {/* the path: a soft glow under a crisp line, and a moving dash on top */}
      <path id="hg-path" d={d} fill="none" stroke="url(#hg-line)" strokeWidth="1.8" strokeOpacity=".75" />
      <path d={d} fill="none" stroke="#fff" strokeOpacity=".14" strokeWidth="1.2" className="flow-dash" />

      {/* a signal that travels the whole way */}
      <circle r="3.5" fill="#DCE4FF" fillOpacity=".8">
        <animateMotion dur="6s" repeatCount="indefinite" rotate="auto">
          <mpath href="#hg-path" />
        </animateMotion>
      </circle>

      {/* declined */}
      <g>
        <circle cx={no.x} cy={no.y} r="30" fill="#1E1A24" stroke="#C8676B" strokeWidth="1.6" />
        <path d={`M ${no.x - 9} ${no.y - 9} L ${no.x + 9} ${no.y + 9} M ${no.x + 9} ${no.y - 9} L ${no.x - 9} ${no.y + 9}`}
          stroke="#E59A9D" strokeWidth="2.8" strokeLinecap="round" />
        <text x={no.x} y={no.y + 56} textAnchor="middle" fill="#D99396" fontSize="14" fontWeight="600">{t.hero.g.no}</text>
      </g>

      {/* the four things the agent does */}
      {pts.slice(1, -1).map((p, i) => {
        const above = p.y < 250;
        return (
          <g key={p.key}>
            <circle cx={p.x} cy={p.y} r="22" fill="#0C2740" stroke="#6F88C9" strokeOpacity=".25"
              style={{ animation: `pulse-node 7s ease-in-out ${1.1 * (i + 1)}s infinite` }} />
            <circle cx={p.x} cy={p.y} r="15" fill="#123352" stroke="#6F88C9" strokeWidth="1.4" />
            <circle cx={p.x} cy={p.y} r="3.5" fill="#B5C3E8" />
            <text x={p.x} y={above ? p.y - 36 : p.y + 46} textAnchor="middle" fill="rgba(255,255,255,.72)"
              fontSize="14" fontWeight="500">{t.hero.g[p.key]}</text>
          </g>
        );
      })}

      {/* approved */}
      <g>
        <circle cx={yes.x} cy={yes.y} r="44" fill="#0E2F33" stroke="#3FA593" strokeWidth="1.8" />
        <path d={`M ${yes.x - 16} ${yes.y + 1} l 10 10 l 21 -22`} fill="none" stroke="#7CCFBE" strokeWidth="4.2"
          strokeLinecap="round" strokeLinejoin="round" />
        <text x={yes.x} y={yes.y + 74} textAnchor="middle" fill="#8ACFC1" fontSize="15" fontWeight="600">{t.hero.g.yes}</text>
      </g>
    </svg>
  );
}
