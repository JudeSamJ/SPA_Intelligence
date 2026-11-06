import { gsap, ScrollToPlugin } from "./registry";

void ScrollToPlugin;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let smoother: any = null;
/** The landing page registers its ScrollSmoother here so anchor navigation works with and without it. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const setSmoother = (s: any) => void (smoother = s);
export const getScrollY = () => (smoother ? (smoother.scrollTop() as number) : window.scrollY);

/** ScrollToPlugin (or the smoother) anchor navigation. */
export function scrollToTarget(target: string | Element, offset = 70, instant = false) {
  if (smoother) return void smoother.scrollTo(target, !instant, `top ${offset}px`);
  gsap.to(window, {
    scrollTo: { y: target, offsetY: offset },
    duration: instant ? 0 : 1.1,
    ease: "power3.inOut",
  });
}
