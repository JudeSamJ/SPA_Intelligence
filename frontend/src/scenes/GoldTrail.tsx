import { useEffect, useRef } from "react";
import { gsap } from "../motion/registry";
import { usePrefs } from "../state/prefs";

/** Cursor trail of gold dust: landing page, desktop, full effects only. A fixed pool of 22 reused elements. */
export function GoldTrail() {
  const layer = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();
  useEffect(() => {
    const host = layer.current;
    const fine = window.matchMedia("(pointer: fine)").matches && window.innerWidth >= 1024;
    if (!host || tier !== "full" || !fine) return;
    const pool = Array.from({ length: 22 }, () => {
      const d = document.createElement("i");
      Object.assign(d.style, {
        position: "fixed",
        left: "0",
        top: "0",
        width: "5px",
        height: "5px",
        borderRadius: "50%",
        background: "radial-gradient(circle, #ffe6a3, #d4a24c)",
        opacity: "0",
        pointerEvents: "none",
        zIndex: "60",
      });
      host.appendChild(d);
      return d;
    });
    let i = 0,
      last = 0;
    const move = (e: PointerEvent) => {
      const now = performance.now();
      if (now - last < 40) return;
      last = now;
      const d = pool[i++ % pool.length]!;
      gsap.killTweensOf(d);
      gsap.set(d, { x: e.clientX, y: e.clientY, opacity: 0.9, scale: 1 });
      gsap.to(d, {
        x: e.clientX + gsap.utils.random(-14, 14),
        y: e.clientY + gsap.utils.random(6, 26),
        opacity: 0,
        scale: 0.2,
        duration: 0.8,
        ease: "power2.out",
      });
    };
    window.addEventListener("pointermove", move);
    return () => {
      window.removeEventListener("pointermove", move);
      pool.forEach((d) => d.remove());
    };
  }, [tier]);
  return <div ref={layer} aria-hidden="true" />;
}
