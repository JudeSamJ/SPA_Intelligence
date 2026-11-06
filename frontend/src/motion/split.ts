import { gsap, SplitText } from "./registry";

/**
 * SplitText headline reveal. Arabic must NOT be split into characters (breaks letter joining), so RTL/Arabic text
 * uses words + lines only. Returns a cleanup that reverts the split.
 */
export function splitReveal(
  el: HTMLElement,
  opts: { rtl: boolean; delay?: number; scroll?: boolean; stagger?: number } = { rtl: false },
) {
  const rtl = opts.rtl || /[؀-ۿ]/.test(el.textContent ?? "");
  const split = SplitText.create(el, {
    type: rtl ? "words,lines" : "chars,words,lines",
    mask: "lines",
    linesClass: "split-line",
    autoSplit: true,
    onSplit: (self: SplitText) => {
      const targets = rtl ? self.words : self.chars;
      return gsap.from(targets, {
        yPercent: 110,
        opacity: 0,
        rotate: rtl ? 0 : 4,
        duration: 0.9,
        delay: opts.delay ?? 0,
        ease: "dune",
        stagger: { each: opts.stagger ?? (rtl ? 0.08 : 0.018), from: "start" },
      });
    },
  });
  return () => split.revert();
}
