import { palmPaths } from "./art";

/** First point of a path ("M x y ..."): where a frond is attached to the trunk, used as its growth origin. */
const origin = (d: string) => {
  const m = /^M\s*([\d.]+)\s+([\d.]+)/.exec(d);
  return m ? `${m[1]} ${m[2]}` : "400 600";
};

/**
 * Palm Jumeirah-style aerial island (trunk + fronds + crescent breakwater) over the sea.
 * Animated in time (not by scroll): ripples spread, the trunk rises, fronds sprout, the crescent sweeps, a plane flies.
 */
export function Palm({ className }: { className?: string }) {
  const { trunk, crescent, fronds } = palmPaths();
  return (
    <svg
      className={className}
      style={{ overflow: "visible" }}
      viewBox="0 0 800 800"
      role="img"
      aria-label="Palm-shaped island rising from the sea, line drawing"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <defs>
        <radialGradient id="palm-glow" cx="50%" cy="62%" r="55%">
          <stop offset="0" stopColor="#d4a24c" stopOpacity="0.28" />
          <stop offset="1" stopColor="#d4a24c" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle className="palm-glow" cx="400" cy="500" r="330" fill="url(#palm-glow)" stroke="none" />
      <g className="ripples" stroke="currentColor" strokeWidth="1.4" opacity="0.9">
        {[0, 1, 2].map((i) => (
          <ellipse key={i} className="ripple" cx="400" cy="752" rx="150" ry="30" />
        ))}
      </g>
      <g strokeWidth="3" opacity="0.95">
        <path id="palm-crescent" className="draw crescent" d={crescent} />
        <path className="draw trunk" d={trunk} strokeWidth="5" />
        {fronds.map((d, i) => (
          <path
            key={i}
            className="frond"
            d={d}
            strokeWidth="2.6"
            data-origin={origin(d)}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <path className="draw ring" d="M 90 345 A 322 322 0 0 1 710 345" strokeWidth="1.5" opacity=".6" />
        <path className="draw ring" d="M 70 360 A 345 345 0 0 1 730 360" strokeWidth="1" opacity=".4" />
      </g>
      <g className="payload">
        <circle id="palm-marker" cx="400" cy="320" r="0" fill="currentColor" />
      </g>
    </svg>
  );
}
