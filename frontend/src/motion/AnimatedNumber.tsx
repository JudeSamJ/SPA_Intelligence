import { useEffect, useRef } from "react";
import { usePrefs } from "../state/prefs";
import { gsap } from "./registry";

interface Props {
  value: number;
  format: (n: number) => string;
  duration?: number;
  className?: string;
}

/**
 * Counter that ALWAYS settles on the exact API value: every code path (completion, interruption by a new
 * value, unmount, reduced effects) finishes by writing format(value). The accessible name is the final value.
 */
export function AnimatedNumber({ value, format, duration = 0.9, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef<number | null>(null);
  const { tier } = usePrefs();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const settle = () => {
      el.textContent = format(value);
      shown.current = value;
    };
    const from = shown.current ?? 0;
    if (tier === "reduced" || from === value) {
      settle();
      return;
    }
    const proxy = { v: from };
    const tween = gsap.to(proxy, {
      v: value,
      duration: shown.current === null ? duration * 1.4 : Math.min(duration, 0.5),
      ease: "power3.out",
      onUpdate: () => {
        el.textContent = format(proxy.v);
      },
      onComplete: settle,
    });
    return () => {
      tween.kill();
      settle(); // never leave an intermediate number in the DOM
    };
  }, [value, format, duration, tier]);

  return (
    <span ref={ref} className={`num ${className ?? ""}`} aria-label={format(value)} data-final={value} />
  );
}
