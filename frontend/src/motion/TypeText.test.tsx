import gsap from "gsap";
import { TextPlugin } from "gsap/TextPlugin";
import { describe, expect, it } from "vitest";
import { escapeForTextPlugin } from "./TypeText";

gsap.registerPlugin(TextPlugin);

// REAL gsap + REAL TextPlugin: proves untrusted text can never create elements while "typing".
describe("typewriter is plain-text only", () => {
  const payloads = [
    "<img src=x onerror=alert(1)>",
    "Page 3: <b>bold</b> & <script>alert(1)</script>",
    "&lt;img src=x onerror=alert(1)&gt; &amp;",
    `"quoted" 'single' <svg/onload=alert(1)>`,
  ];
  for (const text of payloads) {
    it(`no elements at 25/50/75/100% for ${JSON.stringify(text).slice(0, 36)}`, () => {
      const el = document.createElement("span");
      document.body.appendChild(el);
      const tw = gsap.to(el, {
        duration: 1,
        text: { value: escapeForTextPlugin(text), delimiter: "" },
        ease: "none",
        paused: true,
      });
      for (const p of [0.25, 0.5, 0.75, 1]) {
        tw.progress(p);
        expect(el.querySelector("*")).toBeNull();
      }
      el.textContent = text; // the component always finishes with textContent
      expect(el.textContent).toBe(text);
      expect(el.querySelector("*")).toBeNull();
      el.remove();
    });
  }
});
