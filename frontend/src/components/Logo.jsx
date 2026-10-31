// Logo A: a blue-to-navy tile with a teal tick (teal = approved, the only place it is "decoration").
export default function Logo({ size = 32, word = true, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
        <defs>
          <linearGradient id="ny-tile" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#3D6BFF" />
            <stop offset="1" stopColor="#0C2740" />
          </linearGradient>
        </defs>
        <rect width="40" height="40" rx="10" fill="url(#ny-tile)" />
        <rect x=".5" y=".5" width="39" height="39" rx="9.5" fill="none" stroke="rgba(255,255,255,.18)" />
        <path d="M11 20.5l6 6L29.5 13" fill="none" stroke="#12B39A" strokeWidth="4.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {word && <span className="font-bold text-[21px] tracking-tight" dir="ltr">NextYes</span>}
    </span>
  );
}
