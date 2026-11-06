import { useEffect, useRef } from "react";
import { usePrefs } from "../state/prefs";
import { gsap } from "./registry";

/** Decode effect (ScrambleTextPlugin) on entrance only. It resolves to EXACTLY `text` and never loops. */
export function ScrambleValue({
  text,
  delay = 0,
  className,
}: {
  text: string;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const { tier } = usePrefs();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = text;
    if (tier !== "full" || !text.trim()) return;
    const tween = gsap.fromTo(
      el,
      { scrambleText: { text: "", chars: "0123456789ABCDEF·", speed: 0.5 } },
      {
        duration: 0.8,
        delay,
        scrambleText: { text, chars: "0123456789ABCDEF·", revealDelay: 0.15, speed: 0.6 },
        ease: "none",
        onComplete: () => void (el.textContent = text),
      },
    );
    return () => {
      tween.kill();
      el.textContent = text;
    };
  }, [text, delay, tier]);

  return <span ref={ref} className={className} aria-label={text} />;
}
