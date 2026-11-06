import { useEffect, useRef } from "react";
import { gsap, loadMorph } from "../motion/registry";
import type { Theme } from "../state/prefs";

export const SUN_D = "M12 4 a8 8 0 1 0 0.001 0 Z";
export const MOON_D = "M12 4 a8 8 0 1 0 8 10 a6.5 6.5 0 0 1 -8 -10 Z";

/** Theme toggle icon: the shape MORPHS sun -> moon (MorphSVGPlugin). */
export function SunMoon({ theme, animate }: { theme: Theme; animate: boolean }) {
  const shape = useRef<SVGPathElement>(null);
  const rays = useRef<SVGGElement>(null);
  const first = useRef(true);

  useEffect(() => {
    const el = shape.current;
    if (!el) return;
    const target = theme === "dusk" ? MOON_D : SUN_D;
    if (first.current || !animate) {
      first.current = false;
      el.setAttribute("d", target);
      gsap.set(rays.current, { opacity: theme === "dusk" ? 0 : 1 });
      return;
    }
    let tween: gsap.core.Tween | undefined;
    void loadMorph().then(() => {
      tween = gsap.to(el, {
        duration: 0.8,
        morphSVG: { shape: target, shapeIndex: "auto" },
        ease: "power3.inOut",
      });
      gsap.to(rays.current, {
        duration: 0.5,
        opacity: theme === "dusk" ? 0 : 1,
        rotate: theme === "dusk" ? -90 : 0,
        transformOrigin: "50% 50%",
      });
    });
    return () => void tween?.kill();
  }, [theme, animate]);

  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      aria-hidden="true"
      fill="currentColor"
      stroke="currentColor"
      strokeWidth="0.6"
    >
      <path ref={shape} d={SUN_D} />
      <g ref={rays} strokeWidth="1.6" strokeLinecap="round" fill="none">
        {Array.from({ length: 8 }, (_, i) => {
          const a = (i * Math.PI) / 4;
          return (
            <line
              key={i}
              x1={12 + Math.cos(a) * 9.5}
              y1={12 + Math.sin(a) * 9.5}
              x2={12 + Math.cos(a) * 11.4}
              y2={12 + Math.sin(a) * 11.4}
            />
          );
        })}
      </g>
    </svg>
  );
}
