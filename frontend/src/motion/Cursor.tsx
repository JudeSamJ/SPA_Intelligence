import { useEffect, useRef } from "react";
import { usePrefs } from "../state/prefs";
import { gsap } from "./registry";

/** Custom cursor: desktop pointer + full effects only. Native cursor stays on form controls and links (see CSS). */
export function Cursor() {
  const dot = useRef<HTMLDivElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();

  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches && window.innerWidth >= 1024;
    if (tier !== "full" || !fine || !dot.current || !ring.current) return;
    document.body.classList.add("has-custom-cursor");
    const dx = gsap.quickTo(dot.current, "x", { duration: 0.08 });
    const dy = gsap.quickTo(dot.current, "y", { duration: 0.08 });
    const rx = gsap.quickTo(ring.current, "x", { duration: 0.45, ease: "power3.out" });
    const ry = gsap.quickTo(ring.current, "y", { duration: 0.45, ease: "power3.out" });
    const move = (e: PointerEvent) => {
      dx(e.clientX);
      dy(e.clientY);
      rx(e.clientX);
      ry(e.clientY);
    };
    const over = (e: PointerEvent) => {
      const hot = (e.target as HTMLElement | null)?.closest("a,button,[data-cursor]");
      gsap.to(ring.current, { scale: hot ? 1.9 : 1, duration: 0.3 });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerover", over);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerover", over);
      document.body.classList.remove("has-custom-cursor");
    };
  }, [tier]);

  if (tier !== "full") return null;
  const base = {
    position: "fixed",
    top: 0,
    left: 0,
    pointerEvents: "none",
    zIndex: 90,
    borderRadius: "50%",
  } as const;
  return (
    <div aria-hidden="true">
      <div
        ref={ring}
        style={{
          ...base,
          width: 34,
          height: 34,
          margin: "-17px 0 0 -17px",
          border: "1.5px solid var(--gold)",
          mixBlendMode: "difference",
        }}
      />
      <div
        ref={dot}
        style={{ ...base, width: 7, height: 7, margin: "-3.5px 0 0 -3.5px", background: "var(--gold)" }}
      />
    </div>
  );
}
