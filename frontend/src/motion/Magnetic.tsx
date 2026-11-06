import { useEffect, useRef, type ReactNode } from "react";
import { usePrefs } from "../state/prefs";
import { gsap } from "./registry";

/** Magnetic hover for buttons: quickTo x/y toward the pointer. Disabled for touch and reduced effects. */
export function Magnetic({ children, strength = 0.35 }: { children: ReactNode; strength?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const { tier } = usePrefs();
  useEffect(() => {
    const el = ref.current;
    if (!el || tier !== "full") return;
    const x = gsap.quickTo(el, "x", { duration: 0.5, ease: "elastic.out(1, 0.5)" });
    const y = gsap.quickTo(el, "y", { duration: 0.5, ease: "elastic.out(1, 0.5)" });
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      x((e.clientX - (r.left + r.width / 2)) * strength);
      y((e.clientY - (r.top + r.height / 2)) * strength);
    };
    const leave = () => {
      x(0);
      y(0);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      gsap.set(el, { clearProps: "x,y" });
    };
  }, [tier, strength]);
  return (
    <span ref={ref} style={{ display: "inline-block" }}>
      {children}
    </span>
  );
}
