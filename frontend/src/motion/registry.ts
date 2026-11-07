/**
 * The ONE place GSAP plugins are registered.
 *  - core plugins: registered eagerly (small, used on most screens)
 *  - heavy / situational plugins: loaded lazily via dynamic import so they code-split
 *  - dev-only tools (GSDevTools, MotionPathHelper): behind import.meta.env.DEV so the production bundle never contains them
 * GSAP 3.15 ships all plugins in the public npm package (Standard "no charge" licence).
 */
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { CustomBounce } from "gsap/CustomBounce";
import { CustomEase } from "gsap/CustomEase";
import { CustomWiggle } from "gsap/CustomWiggle";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { ExpoScaleEase, RoughEase, SlowMo } from "gsap/EasePack";
import { Flip } from "gsap/Flip";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { ScrollToPlugin } from "gsap/ScrollToPlugin";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { TextPlugin } from "gsap/TextPlugin";

let coreDone = false;
export function registerCore() {
  if (coreDone) return;
  coreDone = true;
  gsap.registerPlugin(
    useGSAP,
    ScrollTrigger,
    ScrollToPlugin,
    TextPlugin,
    SplitText,
    ScrambleTextPlugin,
    DrawSVGPlugin,
    MotionPathPlugin,
    Flip,
    CustomEase,
    CustomWiggle,
    CustomBounce,
    RoughEase,
    SlowMo,
    ExpoScaleEase,
  );
  gsap.defaults({ ease: "power3.out" });
  ScrollTrigger.config({ ignoreMobileResize: true });
}

let morphP: Promise<void> | null = null;
/** MorphSVGPlugin: sun<->moon, day<->night skyline, loader shapes. */
export function loadMorph() {
  morphP ??= import("gsap/MorphSVGPlugin").then((m) => void gsap.registerPlugin(m.MorphSVGPlugin));
  return morphP;
}

let dragP: Promise<void> | null = null;
/** Draggable + InertiaPlugin: delay dial, draggable milestone timeline. */
export function loadDraggable() {
  dragP ??= Promise.all([import("gsap/Draggable"), import("gsap/InertiaPlugin")]).then(
    ([d, i]) => void gsap.registerPlugin(d.Draggable, i.InertiaPlugin),
  );
  return dragP;
}

let physP: Promise<void> | null = null;
/** Physics2DPlugin + PhysicsPropsPlugin: coin burst, falling dust. */
export function loadPhysics() {
  physP ??= Promise.all([import("gsap/Physics2DPlugin"), import("gsap/PhysicsPropsPlugin")]).then(
    ([a, b]) => void gsap.registerPlugin(a.Physics2DPlugin, b.PhysicsPropsPlugin),
  );
  return physP;
}

let smootherP: Promise<typeof import("gsap/ScrollSmoother")> | null = null;
/** ScrollSmoother: landing page only. */
export function loadSmoother() {
  smootherP ??= import("gsap/ScrollSmoother").then((m) => {
    gsap.registerPlugin(m.ScrollSmoother);
    return m;
  });
  return smootherP;
}

/** Dev-only: ?devtools=1 in `vite dev`. This whole block is removed from production builds. */
export async function loadDevtools() {
  if (import.meta.env.DEV) {
    if (new URLSearchParams(window.location.search).get("devtools") !== "1") return;
    const [dt, mp] = await Promise.all([import("gsap/GSDevTools"), import("gsap/MotionPathHelper")]);
    gsap.registerPlugin(dt.GSDevTools, mp.MotionPathHelper);
    dt.GSDevTools.create();
    (window as unknown as { __motionPathHelper?: unknown }).__motionPathHelper = mp.MotionPathHelper;
  }
}

registerCore();
export {
  CustomBounce,
  CustomWiggle,
  CustomEase,
  Flip,
  gsap,
  ScrollToPlugin,
  ScrollTrigger,
  SplitText,
  useGSAP,
};
