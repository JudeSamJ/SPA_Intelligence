import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useFmt } from "../i18n/format";
import { gsap, loadDraggable } from "../motion/registry";
import { usePrefs } from "../state/prefs";

const SWEEP = 270; // degrees of travel
const MIN_ROT = -SWEEP / 2;

interface Props {
  value: number;
  max: number;
  presets: number[];
  onChange: (days: number) => void;
}

const angleFor = (v: number, max: number) => MIN_ROT + (Math.min(Math.max(v, 0), max) / max) * SWEEP;
const valueFor = (rot: number, max: number) => Math.round(((rot - MIN_ROT) / SWEEP) * max);

/**
 * Draggable rotary dial with inertia (Draggable + InertiaPlugin) that snaps to the scenario presets.
 * Fully keyboard accessible (role=slider; arrows, PageUp/Down, Home/End) and mirrored by preset buttons.
 * The number it shows is only the *input* (days); every amount comes from the API.
 */
export function PenaltyDial({ value, max, presets, onChange }: Props) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { tier } = usePrefs();
  const knob = useRef<SVGGElement>(null);
  const draggable = useRef<{ kill: () => void } | null>(null);
  const fromDrag = useRef(false);
  const latest = useRef({ onChange, max, presets });
  latest.current = { onChange, max, presets };

  // follow external value changes (keyboard, presets)
  useEffect(() => {
    if (fromDrag.current || !knob.current) return;
    gsap.to(knob.current, {
      rotation: angleFor(value, max),
      duration: tier === "reduced" ? 0 : 0.45,
      ease: "power3.out",
      transformOrigin: "50% 50%",
      svgOrigin: "100 100",
    });
  }, [value, max, tier]);

  useEffect(() => {
    let dead = false;
    void loadDraggable().then(async () => {
      if (dead || !knob.current) return;
      const { Draggable } = await import("gsap/Draggable");
      gsap.set(knob.current, { rotation: angleFor(value, max), svgOrigin: "100 100" });
      const [d] = Draggable.create(knob.current, {
        type: "rotation",
        bounds: { minRotation: MIN_ROT, maxRotation: MIN_ROT + SWEEP },
        inertia: true,
        snap: (end: number) => {
          const { max: m, presets: ps } = latest.current;
          const near = ps.reduce(
            (a, p) => (Math.abs(angleFor(p, m) - end) < Math.abs(angleFor(a, m) - end) ? p : a),
            ps[0] ?? 0,
          );
          return Math.abs(angleFor(near, m) - end) < 14 ? angleFor(near, m) : end;
        },
        onPress: () => void (fromDrag.current = true),
        onDrag() {
          latest.current.onChange(valueFor(this.rotation, latest.current.max));
        },
        onThrowUpdate() {
          latest.current.onChange(valueFor(this.rotation, latest.current.max));
        },
        onRelease() {
          /* settle handled by throw */
        },
        onThrowComplete() {
          fromDrag.current = false;
          latest.current.onChange(valueFor(this.rotation, latest.current.max));
        },
      });
      draggable.current = d as unknown as { kill: () => void };
    });
    return () => {
      dead = true;
      draggable.current?.kill();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 1;
    const map: Record<string, number> = {
      ArrowRight: step,
      ArrowUp: step,
      ArrowLeft: -step,
      ArrowDown: -step,
      PageUp: 30,
      PageDown: -30,
    };
    let next: number | null = null;
    if (e.key in map) next = value + map[e.key]!;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = max;
    if (next === null) return;
    e.preventDefault();
    fromDrag.current = false;
    onChange(Math.min(max, Math.max(0, next)));
  };

  const ticks = presets.map((p) => ({ p, a: angleFor(p, max) }));
  const pt = (a: number, r: number) => {
    const rad = ((a - 90) * Math.PI) / 180;
    return [100 + Math.cos(rad) * r, 100 + Math.sin(rad) * r] as const;
  };
  return (
    <div style={{ display: "grid", gap: 10, justifyItems: "center" }}>
      <div
        role="slider"
        tabIndex={0}
        aria-label={t("penalty.dial")}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={`${fmt.num(value)} ${t("common.days")}`}
        onKeyDown={onKey}
        data-testid="dial"
        style={{ width: "min(280px, 80vw)", touchAction: "none", borderRadius: "50%" }}
      >
        <svg
          viewBox="0 0 200 200"
          width="100%"
          aria-hidden="true"
          style={{ overflow: "visible", direction: "ltr" }}
        >
          <circle cx="100" cy="100" r="88" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
          <path
            d={`M ${pt(MIN_ROT, 76).join(" ")} A 76 76 0 1 1 ${pt(MIN_ROT + SWEEP, 76).join(" ")}`}
            fill="none"
            stroke="var(--line)"
            strokeWidth="6"
            strokeLinecap="round"
          />
          {ticks.map(({ p, a }) => {
            const [x1, y1] = pt(a, 66),
              [x2, y2] = pt(a, 86),
              [lx, ly] = pt(a, 98);
            return (
              <g key={p}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="var(--accent)"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <text
                  x={lx}
                  y={ly}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="9"
                  fill="var(--muted)"
                  className="num"
                >
                  {fmt.num(p)}
                </text>
              </g>
            );
          })}
          <g ref={knob} style={{ cursor: "grab" }} data-cursor>
            <circle cx="100" cy="100" r="50" fill="var(--surface-2)" stroke="var(--accent)" strokeWidth="2" />
            <path d="M100 56 L108 100 L92 100 Z" fill="var(--accent-fill)" />
            <circle cx="100" cy="100" r="7" fill="var(--accent-fill)" />
          </g>
          <text x="100" y="140" textAnchor="middle" fontSize="10" fill="var(--muted)">
            {t("common.days")}
          </text>
          <text
            x="100"
            y="128"
            textAnchor="middle"
            fontSize="20"
            fontWeight="700"
            fill="var(--fg)"
            className="num"
            data-testid="dial-days"
          >
            {fmt.num(value)}
          </text>
        </svg>
      </div>
      <small style={{ color: "var(--muted)", textAlign: "center" }}>{t("penalty.dialHelp")}</small>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
        {presets.map((p) => (
          <button
            key={p}
            className="chip num"
            aria-pressed={value === p}
            onClick={() => {
              fromDrag.current = false;
              onChange(p);
            }}
            style={{ borderColor: value === p ? "var(--accent)" : undefined }}
          >
            {fmt.num(p)} {t("penalty.daysUnit")}
          </button>
        ))}
      </div>
    </div>
  );
}
