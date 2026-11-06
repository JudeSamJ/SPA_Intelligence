import { useGSAP } from "@gsap/react";
import type { RefObject } from "react";
import { usePrefs, type Tier } from "../state/prefs";
import { gsap, registerCore } from "./registry";

export interface MotionEnv {
  tier: Tier;
  /** viewport >= 768px */
  desktop: boolean;
  rtl: boolean;
  /** +1 in LTR, -1 in RTL: multiply horizontal offsets by this so animations mirror */
  dirSign: 1 | -1;
}

/**
 * Standard entry point for component animation. Wraps `useGSAP` (automatic cleanup/revert) and
 * `gsap.matchMedia()` (desktop vs mobile). The `tier` (full / lite / reduced) comes from user preference,
 * so "reduce effects" works even when the OS setting is off.
 * `setup` may return a cleanup function.
 */
export function useMotion(
  scope: RefObject<HTMLElement | null>,
  setup: (env: MotionEnv) => void | (() => void),
  deps: unknown[] = [],
) {
  const { tier, dir } = usePrefs();
  useGSAP(
    () => {
      registerCore();
      const mm = gsap.matchMedia();
      mm.add({ desktop: "(min-width: 768px)", mobile: "(max-width: 767px)" }, (ctx) => {
        const c = ctx.conditions as { desktop?: boolean };
        return setup({ tier, desktop: !!c.desktop, rtl: dir === "rtl", dirSign: dir === "rtl" ? -1 : 1 });
      });
      return () => mm.revert();
    },
    { scope, dependencies: [tier, dir, ...deps], revertOnUpdate: true },
  );
}
