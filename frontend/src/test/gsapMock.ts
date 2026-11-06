/** Minimal GSAP stand-in for component tests (GSAP plugins are not exercised in jsdom). */
import { vi } from "vitest";

export const controls = { complete: true, lastTween: null as null | { vars: Record<string, unknown> } };

const tween = () => ({
  kill: vi.fn(),
  progress: vi.fn(),
  pause: vi.fn(),
  play: vi.fn(),
  scrollTrigger: undefined,
});
const tl = (): Record<string, unknown> => {
  const t: Record<string, unknown> = {};
  for (const m of ["to", "from", "fromTo", "add", "addLabel", "set", "call"]) t[m] = () => t;
  t.progress = vi.fn();
  t.kill = vi.fn();
  t.scrollTrigger = undefined;
  return t;
};

export const gsap = {
  registerPlugin: vi.fn(),
  defaults: vi.fn(),
  config: vi.fn(),
  to: vi.fn((target: unknown, vars: Record<string, unknown>) => {
    controls.lastTween = { vars };
    if (target && typeof target === "object" && "v" in (target as object)) {
      const proxy = target as { v: number };
      const mid = proxy.v + ((vars.v as number) - proxy.v) / 2;
      if (vars.onUpdate) {
        proxy.v = mid;
        (vars.onUpdate as () => void)();
      }
      if (controls.complete) {
        proxy.v = vars.v as number;
        (vars.onUpdate as (() => void) | undefined)?.();
        (vars.onComplete as (() => void) | undefined)?.();
      }
    } else if (controls.complete) (vars.onComplete as (() => void) | undefined)?.();
    return tween();
  }),
  from: vi.fn(() => tween()),
  set: vi.fn(),
  fromTo: vi.fn((_t: unknown, _a: unknown, b: Record<string, unknown>) => {
    if (controls.complete) (b.onComplete as (() => void) | undefined)?.();
    return tween();
  }),
  quickTo: vi.fn(() => vi.fn()),
  killTweensOf: vi.fn(),
  delayedCall: vi.fn(),
  timeline: vi.fn(() => tl()),
  context: vi.fn(() => ({ revert: vi.fn(), add: vi.fn() })),
  matchMedia: vi.fn(() => ({
    add: (_c: unknown, fn: (ctx: { conditions: Record<string, boolean> }) => unknown) =>
      void fn({ conditions: { desktop: true, mobile: false } }),
    revert: vi.fn(),
  })),
  ticker: { add: vi.fn(), remove: vi.fn() },
  utils: {
    toArray: (x: unknown) => (Array.isArray(x) ? x : x ? [x] : []),
    selector: () => () => [],
    clamp: (a: number, b: number, v: number) => Math.min(b, Math.max(a, v)),
    random: () => 0,
  },
};
const stub = {
  create: vi.fn(),
  getState: vi.fn(() => ({})),
  from: vi.fn(),
  fit: vi.fn(),
  batch: vi.fn(() => []),
  config: vi.fn(),
};
const never = () => new Promise<void>(() => {});

export default {
  gsap,
  registerCore: vi.fn(),
  loadMorph: never,
  loadDraggable: never,
  loadPhysics: never,
  loadSmoother: never,
  loadDevtools: vi.fn(),
  useGSAP: vi.fn(),
  ScrollTrigger: stub,
  ScrollToPlugin: {},
  SplitText: stub,
  Flip: stub,
  Observer: stub,
  CustomEase: stub,
  CustomBounce: stub,
  CustomWiggle: stub,
};
