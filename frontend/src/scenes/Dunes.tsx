import { useId } from "react";
import { duneD } from "./art";

interface Props {
  layers?: number;
  className?: string;
  /** apply the heat-haze displacement filter to the nearest-horizon layer (full effects only) */
  haze?: boolean;
}

const FILLS = ["#7a4a6a", "#a8584a", "#c98a4b", "#a96b36", "#5a3a2a"]; // far -> near: hazy violet to deep umber
/** Layered parallax dunes (original SVG). Each layer carries data-speed (ScrollSmoother) and data-depth (mouse parallax). */
export function Dunes({ layers = 5, className, haze = false }: Props) {
  const id = useId().replace(/:/g, "");
  return (
    <div
      className={className}
      aria-hidden="true"
      style={{ position: "absolute", inset: 0, overflow: "hidden" }}
    >
      {Array.from({ length: layers }, (_, i) => {
        const depth = (i + 1) / layers;
        return (
          <svg
            key={i}
            data-dune
            data-depth={depth.toFixed(2)}
            data-speed={(0.85 + depth * 0.25).toFixed(2)}
            viewBox="0 0 1600 500"
            preserveAspectRatio="none"
            style={{
              position: "absolute",
              insetInline: "-6%",
              bottom: `${-4 + i * 4}%`,
              width: "112%",
              height: `${46 - i * 4}%`,
              filter: haze && i === 1 ? `url(#haze-${id})` : undefined,
            }}
          >
            <defs>
              <pattern
                id={`rip-${id}-${i}`}
                width="14"
                height="9"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(-8)"
              >
                <path
                  d="M0 4.5 Q 3.5 2 7 4.5 T 14 4.5"
                  fill="none"
                  stroke="rgba(255,255,255,.16)"
                  strokeWidth=".9"
                />
              </pattern>
              <linearGradient id={`g-${id}-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={FILLS[i % FILLS.length]} />
                <stop offset="1" stopColor="#1a1222" />
              </linearGradient>
            </defs>
            <path d={duneD(11 + i * 7, 1600, 500, 150 + i * 14, 70 - i * 6, 3)} fill={`url(#g-${id}-${i})`} />
            {i >= 2 && (
              <path
                d={duneD(11 + i * 7, 1600, 500, 150 + i * 14, 70 - i * 6, 3)}
                fill={`url(#rip-${id}-${i})`}
                opacity={0.5}
              />
            )}
          </svg>
        );
      })}
      {haze && (
        <svg width="0" height="0" style={{ position: "absolute" }}>
          <filter id={`haze-${id}`} x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence
              data-haze
              type="fractalNoise"
              baseFrequency="0.006 0.035"
              numOctaves={2}
              seed={3}
              result="n"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="n"
              scale={10}
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </svg>
      )}
    </div>
  );
}
