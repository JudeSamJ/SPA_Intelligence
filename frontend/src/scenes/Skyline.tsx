import { useRef } from "react";
import { genericTowers, skylineSilhouetteD, towerRects } from "./art";

/**
 * Generic Dubai-style skyline with ONE original stepped tapering tower (Burj-style silhouette).
 * `data-band` windows group per tower tier so the landing page can light floors up as features scroll by.
 */
export const SKY_D = {
  day: skylineSilhouetteD(3, 1600, 560, 70, 240, 800),
  dusk: skylineSilhouetteD(8, 1600, 560, 110, 300, 800),
};
export function Skyline({
  className,
  bands = 4,
  initialTheme = "dusk",
}: {
  className?: string;
  bands?: number;
  initialTheme?: "day" | "dusk";
}) {
  const d0 = useRef(SKY_D[initialTheme]).current;
  const towerCx = 800,
    base = 560;
  const tiers = towerRects(towerCx, base);
  const towers = genericTowers(7, 26, 1600, 110, 330, [680, 920]);
  return (
    <svg
      className={className}
      style={{ width: "100%", height: "100%", display: "block" }}
      viewBox="0 0 1600 600"
      preserveAspectRatio="xMidYMax slice"
      role="img"
      aria-label="Skyline with a tall stepped tower, decorative"
      aria-hidden="true"
    >
      <path id="skyline-back" d={d0} fill="currentColor" opacity=".35" />
      {towers.map((t, i) => (
        <g key={i} opacity=".8">
          <rect
            x={t.x}
            y={base - t.h}
            width={t.w}
            height={t.h}
            fill="currentColor"
            opacity={0.55 + (i % 3) * 0.1}
          />
          {t.roof === 1 && (
            <rect x={t.x + t.w * 0.4} y={base - t.h - 26} width={t.w * 0.2} height={26} fill="currentColor" />
          )}
          {t.roof === 2 && (
            <path
              d={`M${t.x} ${base - t.h} L${t.x + t.w / 2} ${base - t.h - 30} L${t.x + t.w} ${base - t.h} Z`}
              fill="currentColor"
            />
          )}
          {Array.from({ length: Math.floor(t.h / 26) }, (_, r) => (
            <rect
              key={r}
              data-win
              x={t.x + t.w * 0.2}
              y={base - t.h + 12 + r * 26}
              width={t.w * 0.6}
              height={5}
              fill="#f6d58a"
              opacity="0"
            />
          ))}
        </g>
      ))}
      <g id="burj">
        {tiers.map((t) => (
          <g key={t.i} data-tier={t.i} data-band={t.i % bands}>
            <rect x={t.x} y={t.y} width={t.w} height={t.h} fill="currentColor" />
            {Array.from({ length: Math.floor(t.h / 14) }, (_, r) => (
              <rect
                key={r}
                data-win
                data-band={t.i % bands}
                x={t.x + t.w * 0.18}
                y={t.y + 7 + r * 14}
                width={t.w * 0.64}
                height={4}
                fill="#f6d58a"
                opacity="0"
              />
            ))}
          </g>
        ))}
        <path
          d={`M${towerCx} ${(tiers.at(-1)?.y ?? 300) - 4} L${towerCx} ${(tiers.at(-1)?.y ?? 300) - 150}`}
          stroke="currentColor"
          strokeWidth="5"
        />
        <circle
          id="burj-beacon"
          cx={towerCx}
          cy={(tiers.at(-1)?.y ?? 300) - 150}
          r="5"
          fill="#ff9d5c"
          opacity="0"
        />
      </g>
      <rect x="0" y={base} width="1600" height="40" fill="currentColor" />
    </svg>
  );
}
