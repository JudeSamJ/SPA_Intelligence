import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Obligation } from "../api/trust";
import { useFmt } from "../i18n/format";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";

const COLOR: Record<string, string> = { high: "var(--danger)", medium: "var(--warn)", low: "var(--info)", none: "var(--muted)" };
const day = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000;

/** Timeline: dots by due date, severity colours, a "today" marker that travels along the line (MotionPath, entrance only). */
export function ObligationTimeline({ rows, asOf }: { rows: Obligation[]; asOf: string }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const ref = useRef<HTMLDivElement>(null);
  const pathId = "tl" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const days = rows.map((r) => day(r.due_date));
  const a = day(asOf);
  const lo = Math.min(a, ...days), hi = Math.max(a, ...days, lo + 1);
  const W = 1000, pad = 40;
  const x = (d: number) => pad + ((d - lo) / (hi - lo)) * (W - 2 * pad);
  // stagger labels over 3 lanes so they do not overlap
  useMotion(ref, ({ tier }) => {
    const m = ref.current?.querySelector("[data-today]");
    if (!m || tier === "reduced") return;
    const end = (a - lo) / (hi - lo);
    gsap.fromTo(m, { opacity: 0 }, { opacity: 1, duration: 0.2 });
    gsap.to(m, { duration: 1.1, ease: "power2.out", motionPath: { path: `#${pathId}`, align: `#${pathId}`, alignOrigin: [0.5, 0.5], start: 0, end } });
  }, [rows.length, asOf]);
  if (!rows.length) return null;
  return (
    <div ref={ref}><svg viewBox={`0 0 ${W} 190`} role="img" aria-label={t("obl.timeline")} style={{ width: "100%", height: "auto" }} data-testid="obl-timeline">
      <path id={pathId} d={`M${pad} 60 C${pad + 300} 60 ${W - pad - 300} 60 ${W - pad} 60`} stroke="var(--line)" strokeWidth={3} fill="none" />
      {rows.map((r, i) => {
        const cx = x(day(r.due_date));
        const ly = 90 + (i % 3) * 34;
        return (
          <g key={r.id} data-testid="obl-dot" data-severity={r.severity}>
            <line x1={cx} x2={cx} y1={60} y2={ly - 12} stroke={COLOR[r.severity]} strokeOpacity={0.4} />
            <circle cx={cx} cy={60} r={7} fill={COLOR[r.severity]} stroke="var(--surface)" strokeWidth={2}><title>{r.label}</title></circle>
            <text x={cx} y={ly} textAnchor="middle" fontSize={13} fill="var(--fg)">{fmt.date(r.due_date)}</text>
          </g>
        );
      })}
      <g data-today transform={`translate(${x(a)} 60)`}>
        <circle r={10} fill="none" stroke="var(--gold)" strokeWidth={3} />
        <text y={-18} textAnchor="middle" fontSize={12} fill="var(--gold)" fontWeight={700}>{t("obl.today")}</text>
      </g>
    </svg></div>
  );
}
