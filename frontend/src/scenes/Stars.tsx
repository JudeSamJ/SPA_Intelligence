import { useRef } from "react";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";
import { rng } from "./art";

/** Twinkling stars (dusk theme). Decorative; fewer on lite tier, none on reduced. */
export function Stars({ count = 70 }: { count?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const r = rng(42);
  const stars = Array.from({ length: count }, () => ({
    x: r() * 100,
    y: r() * 62,
    s: 1 + r() * 2.2,
    o: 0.35 + r() * 0.6,
  }));
  useMotion(ref, ({ tier }) => {
    if (tier === "reduced") return;
    const els = gsap.utils.toArray<HTMLElement>("[data-star]", ref.current);
    gsap.to(tier === "lite" ? els.slice(0, 24) : els, {
      opacity: "random(0.15, 1)",
      duration: "random(0.9, 2.4)",
      repeat: -1,
      yoyo: true,
      stagger: { each: 0.04, from: "random" },
      ease: "sine.inOut",
    });
  });
  return (
    <div
      ref={ref}
      aria-hidden="true"
      data-stars
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      {stars.map((s, i) => (
        <i
          key={i}
          data-star
          style={{
            position: "absolute",
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: s.s,
            height: s.s,
            borderRadius: "50%",
            background: "#fff6d6",
            opacity: s.o,
          }}
        />
      ))}
    </div>
  );
}
