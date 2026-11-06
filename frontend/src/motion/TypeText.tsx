import { useEffect, useRef } from "react";
import { usePrefs } from "../state/prefs";
import { gsap } from "./registry";

/**
 * TextPlugin parses its value as HTML and writes innerHTML. Assistant answers contain untrusted contract text,
 * so the string is HTML-escaped TWICE before it reaches the plugin: the plugin's own decode step
 * leaves one layer of entities, which the innerHTML write then renders as literal characters. The final state is
 * always written with textContent, so the DOM can never contain elements from the answer.
 */
export function escapeForTextPlugin(s: string): string {
  const once = (x: string) =>
    x
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  return once(once(s));
}

interface Props {
  text: string;
  animate: boolean;
  onDone?: () => void;
  className?: string;
}

export function TypeText({ text, animate, onDone, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const { tier } = usePrefs();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const finish = () => {
      el.textContent = text;
      onDone?.();
    };
    if (!animate || tier === "reduced") {
      finish();
      return;
    }
    el.textContent = "";
    const tween = gsap.to(el, {
      duration: Math.min(2.6, Math.max(0.5, text.length * 0.014)),
      text: { value: escapeForTextPlugin(text), delimiter: "" },
      ease: "none",
      onComplete: finish,
    });
    return () => {
      tween.kill();
      el.textContent = text;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, animate, tier]);

  return <span ref={ref} className={className} style={{ whiteSpace: "pre-wrap" }} />;
}
