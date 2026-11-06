import { useId } from "react";

/** Traditional 8-point star lattice (generic Islamic geometry), as a tiled pattern. */
export function MashrabiyaBand({
  className,
  height = 28,
  opacity = 0.5,
}: {
  className?: string;
  height?: number;
  opacity?: number;
}) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      className={className}
      width="100%"
      height={height}
      aria-hidden="true"
      role="presentation"
      style={{ display: "block", opacity }}
    >
      <defs>
        <pattern id={`m-${id}`} width="28" height="28" patternUnits="userSpaceOnUse">
          <g fill="none" stroke="currentColor" strokeWidth="1">
            <rect x="6" y="6" width="16" height="16" />
            <rect x="6" y="6" width="16" height="16" transform="rotate(45 14 14)" />
            <circle cx="14" cy="14" r="3.2" />
          </g>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#m-${id})`} />
    </svg>
  );
}

/** Star path used by the loader (single closed 8-point star) and its circle for MorphSVG. */
export const STAR_D =
  "M50 4 L61 27 L84 16 L73 39 L96 50 L73 61 L84 84 L61 73 L50 96 L39 73 L16 84 L27 61 L4 50 L27 39 L16 16 L39 27 Z";
export const CIRCLE_D =
  "M50 6 C74.3 6 94 25.7 94 50 C94 74.3 74.3 94 50 94 C25.7 94 6 74.3 6 50 C6 25.7 25.7 6 50 6 Z";

/** Loader: the star draws itself (DrawSVG) while an inner shape morphs star <-> circle (MorphSVG). */
export function MashrabiyaLoader({ label, size = 96 }: { label: string; size?: number }) {
  return (
    <div role="status" aria-live="polite" style={{ display: "inline-grid", placeItems: "center", gap: 10 }}>
      <svg
        data-loader
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      >
        <path className="loader-star" d={STAR_D} />
        <path
          className="loader-inner"
          d={CIRCLE_D}
          transform="translate(50 50) scale(.45) translate(-50 -50)"
          strokeWidth="3.5"
          stroke="var(--gold)"
        />
        <rect className="loader-sq" x="22" y="22" width="56" height="56" opacity=".5" />
      </svg>
      <span className="sr-only">{label}</span>
    </div>
  );
}
