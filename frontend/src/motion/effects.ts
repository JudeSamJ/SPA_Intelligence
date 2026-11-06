import type { Tier } from "../state/prefs";
import { EASE } from "./ease";
import { gsap, loadPhysics } from "./registry";

/** Gold-coin / sand-grain burst when a contract finishes extracting. Physics2DPlugin. Skipped when reduced. */
export async function coinBurst(origin: HTMLElement, tier: Tier) {
  if (tier === "reduced") return;
  await loadPhysics();
  const r = origin.getBoundingClientRect();
  const n = tier === "full" ? 26 : 10;
  const layer = document.createElement("div");
  layer.setAttribute("aria-hidden", "true");
  Object.assign(layer.style, {
    position: "fixed",
    inset: "0",
    pointerEvents: "none",
    zIndex: "80",
    overflow: "hidden",
  });
  document.body.appendChild(layer);
  const bits: HTMLElement[] = [];
  for (let i = 0; i < n; i++) {
    const b = document.createElement("i");
    const coin = i % 3 === 0;
    Object.assign(b.style, {
      position: "absolute",
      left: `${r.left + r.width / 2}px`,
      top: `${r.top + r.height / 2}px`,
      width: coin ? "11px" : "5px",
      height: coin ? "11px" : "5px",
      borderRadius: "50%",
      background: coin ? "radial-gradient(circle at 35% 30%, #ffe9a8, #d4a24c 60%, #8a6420)" : "#c98a4b",
    });
    layer.appendChild(b);
    bits.push(b);
  }
  gsap.to(bits, {
    duration: 1.5,
    physics2D: { velocity: "random(220, 560)", angle: "random(-150, -30)", gravity: 900 },
    rotation: "random(-360, 360)",
    opacity: 0,
    ease: EASE.dune,
    stagger: 0.008,
    onComplete: () => layer.remove(),
  });
}

/** Falling dust for error states. PhysicsPropsPlugin. */
export async function dustFall(container: HTMLElement, tier: Tier) {
  if (tier === "reduced") return;
  await loadPhysics();
  const w = container.clientWidth;
  const n = tier === "full" ? 24 : 8;
  const bits: HTMLElement[] = [];
  for (let i = 0; i < n; i++) {
    const b = document.createElement("i");
    b.setAttribute("aria-hidden", "true");
    Object.assign(b.style, {
      position: "absolute",
      top: "0",
      left: `${Math.random() * w}px`,
      width: "4px",
      height: "4px",
      borderRadius: "50%",
      background: "#c98a4b",
      opacity: "0.8",
      pointerEvents: "none",
    });
    container.appendChild(b);
    bits.push(b);
  }
  gsap.to(bits, {
    duration: 2.2,
    physicsProps: {
      y: { velocity: "random(20, 90)", acceleration: 260 },
      x: { velocity: "random(-40, 40)", friction: 0.2 },
    },
    opacity: 0,
    stagger: 0.04,
    onComplete: () => bits.forEach((b) => b.remove()),
  });
}

/**
 * Brief glitch on a title/logo: used ONLY on route transitions and the logo. < 600 ms, a single burst
 * (well under 3 flashes/second), position offsets only, then it settles to clean text.
 */
export function glitchText(el: HTMLElement, tier: Tier) {
  if (tier === "reduced") return;
  const tl = gsap.timeline({ onComplete: () => void gsap.set(el, { clearProps: "textShadow,x,skewX" }) });
  tl.to(el, {
    duration: 0.42,
    x: 3,
    skewX: -6,
    textShadow: "2px 0 #1fb5b0, -2px 0 #e3555a",
    ease: EASE.rough(3, 1),
  }).to(el, { duration: 0.12, x: 0, skewX: 0, textShadow: "0 0 transparent", ease: "power2.out" });
  return tl;
}
