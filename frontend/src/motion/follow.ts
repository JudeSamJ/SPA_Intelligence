import { gsap, ScrollTrigger } from "./registry";

/**
 * Scroll-linked animation with a SPEED LIMIT.
 *
 * A normal scrub follows the scroll position exactly, so one hard flick drives a timeline from 0 to its end in a few
 * frames (measured on the Palm drawing: 0 -> 100% in ~0.5 s, ~14% per 30 ms) and the drawing "skips". Even
 * `scrub: <seconds>` does not help, because its catch-up uses a steep ease that still covers most of the distance in
 * the first third of the time.
 *
 * Here the ScrollTrigger only records the target progress; a ticker moves the timeline toward it with exponential
 * easing (smooth approach, no overshoot) clamped to `maxPerSecond` (timeline progress per second). Scroll as hard as
 * you like: the drawing never advances faster than that. Scrolling back up is limited the same way, so it is symmetric.
 */
export function scrubFollow(
  tl: gsap.core.Timeline,
  vars: ScrollTrigger.Vars,
  { maxPerSecond = 0.22, stiffness = 6 }: { maxPerSecond?: number; stiffness?: number } = {},
) {
  let target = 0;
  let cur = 0;
  let last = performance.now();
  const st = ScrollTrigger.create({
    ...vars,
    onUpdate: (self) => {
      target = self.progress;
    },
    onRefresh: (self) => {
      target = cur = self.progress; // after a resize/reload: start from where the scroll actually is
      tl.progress(cur);
    },
  });
  const tick = () => {
    const now = performance.now();
    const dt = Math.min(0.05, (now - last) / 1000); // ignore long gaps (background tab)
    last = now;
    const d = target - cur;
    if (d === 0) return;
    if (Math.abs(d) < 5e-5) cur = target;
    else {
      const step = d * (1 - Math.exp(-dt * stiffness));
      const cap = maxPerSecond * dt;
      cur += Math.abs(step) > cap ? Math.sign(step) * cap : step;
    }
    tl.progress(cur);
  };
  gsap.ticker.add(tick);
  return {
    st,
    /** re-sync after anything that moved the timeline outside the follower (e.g. pre-warming) */
    resync: () => {
      target = cur = st.progress;
      tl.progress(cur);
    },
    stop: () => {
      gsap.ticker.remove(tick);
      st.kill();
    },
  };
}
