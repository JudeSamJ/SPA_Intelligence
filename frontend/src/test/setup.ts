import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom lacks these; GSAP plugins are mocked per test where needed.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (q: string) => ({
    matches: false,
    media: q,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    onchange: null,
    dispatchEvent: () => false,
  }),
});
class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}
(window as unknown as Record<string, unknown>).IntersectionObserver = IO;
(window as unknown as Record<string, unknown>).ResizeObserver = IO;
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();
