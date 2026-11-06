import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { PlanRow } from "../api/client";
import { useFmt } from "../i18n/format";
import { gsap, loadDraggable } from "../motion/registry";
import { usePrefs } from "../state/prefs";

const W = 1000,
  H = 190,
  PAD = 70;

/**
 * Payment timeline. Node positions come from the due dates in the API response (layout only, no financial maths);
 * a payment dot travels along the path (MotionPathPlugin) to the next upcoming payment; the strip can be dragged
 * with inertia when narrower than the timeline (Draggable + InertiaPlugin).
 */
export function MilestoneTimeline({ plan, asOf }: { plan: PlanRow[]; asOf: string }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { tier, dir } = usePrefs();
  const rtl = dir === "rtl";
  const box = useRef<HTMLDivElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  const path = useRef<SVGPathElement>(null);
  const dot = useRef<SVGCircleElement>(null);

  const nodes = useMemo(() => {
    const dated = plan.filter((p) => p.due_date).map((p) => ({ p, ts: Date.parse(p.due_date as string) }));
    if (!dated.length) return [];
    const min = Math.min(...dated.map((d) => d.ts)),
      max = Math.max(...dated.map((d) => d.ts));
    return dated.map((d, i) => {
      const f = max === min ? 0.5 : (d.ts - min) / (max - min);
      const x = PAD + (rtl ? 1 - f : f) * (W - 2 * PAD);
      return { ...d, x, y: H / 2 + (i % 2 ? -34 : 34), f };
    });
  }, [plan, rtl]);

  const d = useMemo(() => {
    const pts = [...nodes].sort((a, b) => a.x - b.x);
    if (pts.length < 2) return "";
    return pts.reduce((acc, p, i) => {
      if (i === 0) return `M${p.x} ${p.y}`;
      const q = pts[i - 1]!;
      const mx = (q.x + p.x) / 2;
      return `${acc} C${mx} ${q.y} ${mx} ${p.y} ${p.x} ${p.y}`;
    }, "");
  }, [nodes]);

  const nextIdx = nodes.findIndex((n) => (n.p.due_date as string) >= asOf);

  useEffect(() => {
    const el = path.current,
      c = dot.current;
    if (!el || !c || !d) return;
    const total = el.getTotalLength();
    const target = nextIdx === -1 ? nodes[nodes.length - 1] : nodes[nextIdx];
    if (!target) return;
    // length fraction at the target node: nearest sampled point on the path
    let best = 0,
      bestDist = Infinity;
    for (let s = 0; s <= 400; s++) {
      const pt = el.getPointAtLength((s / 400) * total);
      const dist = Math.hypot(pt.x - target.x, pt.y - target.y);
      if (dist < bestDist) {
        bestDist = dist;
        best = s / 400;
      }
    }
    const first = nodes.reduce((a, b) => (a.x < b.x ? a : b));
    c.setAttribute("cx", String(first.x));
    c.setAttribute("cy", String(first.y));
    if (tier === "reduced") {
      c.setAttribute("cx", String(target.x));
      c.setAttribute("cy", String(target.y));
      return;
    }
    const tw = gsap.to(c, {
      duration: 2.2,
      ease: "power2.inOut",
      motionPath: { path: el, align: el, alignOrigin: [0.5, 0.5], start: 0, end: best },
    });
    return () => void tw.kill();
  }, [d, nextIdx, nodes, tier]);

  useEffect(() => {
    let inst: { kill: () => void } | undefined;
    let dead = false;
    void loadDraggable().then(async () => {
      if (dead || !strip.current || !box.current) return;
      const { Draggable } = await import("gsap/Draggable");
      const over = () => Math.max(0, strip.current!.scrollWidth - box.current!.clientWidth);
      if (over() === 0) return;
      [inst] = Draggable.create(strip.current, {
        type: "x",
        inertia: true,
        bounds: { minX: -over(), maxX: 0 },
        edgeResistance: 0.8,
        dragClickables: false,
      }) as unknown as Array<{ kill: () => void }>;
    });
    return () => {
      dead = true;
      inst?.kill();
    };
  }, [nodes.length, rtl]);

  if (!nodes.length) return null;
  return (
    <div
      ref={box}
      data-testid="timeline"
      style={{ overflow: "hidden", direction: "ltr", touchAction: "pan-y" }}
      aria-label={t("cashflow.timeline")}
      role="group"
    >
      <div ref={strip} style={{ width: "max(100%, 760px)", cursor: "grab" }} data-cursor>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={t("cashflow.timeline")}>
          <path ref={path} d={d} fill="none" stroke="var(--line)" strokeWidth="4" strokeLinecap="round" />
          {nodes.map((n, i) => {
            const past = (n.p.due_date as string) < asOf;
            const lab = n.y < H / 2;
            return (
              <g key={i} data-testid="timeline-node">
                <circle
                  cx={n.x}
                  cy={n.y}
                  r="9"
                  fill={past ? "var(--muted)" : n.p.at_risk ? "var(--accent-fill)" : "var(--info)"}
                  stroke="var(--surface)"
                  strokeWidth="3"
                />
                <text
                  x={n.x}
                  y={lab ? n.y - 18 : n.y + 28}
                  textAnchor="middle"
                  fontSize="13"
                  fontWeight="700"
                  fill="var(--fg)"
                  className="num"
                >
                  {fmt.date(n.p.due_date as string)}
                </text>
                <text
                  x={n.x}
                  y={lab ? n.y - 34 : n.y + 44}
                  textAnchor="middle"
                  fontSize="12"
                  fill="var(--muted)"
                  className="num"
                >
                  {fmt.aed(n.p.amount, 0)}
                </text>
              </g>
            );
          })}
          <circle
            ref={dot}
            r="8"
            fill="var(--gold)"
            stroke="var(--fg)"
            strokeWidth="2"
            data-testid="payment-dot"
          />
        </svg>
      </div>
    </div>
  );
}
