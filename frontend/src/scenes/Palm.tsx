import { palmPaths } from "./art";

/** Palm Jumeirah-style aerial line art (crescent + trunk + fronds). Everything is `.draw` for DrawSVGPlugin. */
export function Palm({ className }: { className?: string }) {
  const { trunk, crescent, fronds } = palmPaths();
  return (
    <svg
      className={className}
      viewBox="0 0 800 800"
      role="img"
      aria-label="Palm-shaped island, line drawing"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <g strokeWidth="3" opacity="0.9">
        <path id="palm-crescent" className="draw" d={crescent} />
        <path className="draw" d={trunk} strokeWidth="5" />
        {fronds.map((d, i) => (
          <path key={i} className="draw frond" d={d} strokeWidth="2.6" />
        ))}
        <path className="draw" d="M 90 345 A 322 322 0 0 1 710 345" strokeWidth="1.5" opacity=".6" />
        <path className="draw" d="M 70 360 A 345 345 0 0 1 730 360" strokeWidth="1" opacity=".4" />
      </g>
      <g className="payload">
        <circle id="palm-marker" cx="400" cy="320" r="0" fill="currentColor" />
      </g>
    </svg>
  );
}
