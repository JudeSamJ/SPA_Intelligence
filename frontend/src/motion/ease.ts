import { CustomBounce, CustomEase, CustomWiggle, gsap, registerCore } from "./registry";

registerCore();

/** Named eases, created once. */
CustomEase.create("dune", "M0,0 C0.16,0.84 0.3,1 1,1"); // long soft settle, like sand
CustomEase.create("sunrise", "M0,0 C0.5,0 0.1,1 1,1");
CustomWiggle.create("alertWiggle", { wiggles: 6, type: "easeOut" });
CustomBounce.create("coinBounce", { strength: 0.55, squash: 2, squashID: "coinBounce-squash" });

export const EASE = {
  dune: "dune",
  sunrise: "sunrise",
  wiggle: "alertWiggle",
  bounce: "coinBounce",
  squash: "coinBounce-squash",
  /** RoughEase: jittery, for the glitch bursts only (never on data) */
  rough: (points = 4, strength = 1) =>
    `rough({ strength: ${strength}, points: ${points}, randomize: true, clamp: true })`,
  slow: "slow(0.6, 0.6, false)", // SlowMo: hero reveals
  expoScale: (from: number, to: number) => `expoScale(${from}, ${to})`,
};

export { gsap };
