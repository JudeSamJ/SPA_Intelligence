import { useRef } from "react";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";

const AREAS = ["Palm Jumeirah", "Dubai Marina", "Downtown", "Business Bay", "Yas Island", "Saadiyat"];

/** Decorative ticker of area names (not data). Mirrors direction in RTL. */
export function Marquee({ reverse = false }: { reverse?: boolean }) {
  const track = useRef<HTMLDivElement>(null);
  useMotion(
    track,
    ({ tier, dirSign }) => {
      if (tier === "reduced") return;
      const sign = reverse ? -dirSign : dirSign;
      gsap.fromTo(
        track.current,
        { xPercent: sign === 1 ? 0 : -50 },
        { xPercent: sign === 1 ? -50 : 0, duration: tier === "lite" ? 40 : 28, ease: "none", repeat: -1 },
      );
    },
    [reverse],
  );
  const row = (k: string) => (
    <span key={k} style={{ display: "inline-flex", gap: "2.5rem", paddingInlineEnd: "2.5rem" }}>
      {AREAS.map((a) => (
        <span
          key={a}
          className="display"
          style={{ fontSize: "clamp(1.4rem,3.2vw,2.4rem)", whiteSpace: "nowrap" }}
        >
          {a} <span style={{ color: "var(--gold)" }}>✦</span>
        </span>
      ))}
    </span>
  );
  return (
    <div aria-hidden="true" style={{ overflow: "hidden", whiteSpace: "nowrap", direction: "ltr" }}>
      <div ref={track} style={{ display: "inline-flex", willChange: "transform" }}>
        {row("a")}
        {row("b")}
      </div>
    </div>
  );
}
