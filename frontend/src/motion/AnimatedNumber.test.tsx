import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { controls } from "../test/gsapMock";
import { AnimatedNumber } from "./AnimatedNumber";

vi.mock("./registry", async () => (await import("../test/gsapMock")).default);

const fmt = (n: number) => `AED ${n.toFixed(2)}`;
const wrap = (v: number) => (
  <PrefsProvider>
    <AnimatedNumber value={v} format={fmt} />
  </PrefsProvider>
);
beforeEach(() => {
  controls.complete = true;
});
afterEach(() => {
  controls.complete = true;
});

describe("AnimatedNumber settles on the exact value", () => {
  it("shows exactly the formatted API value after the tween completes", () => {
    const { container } = render(wrap(9863.01));
    expect(container.textContent).toBe("AED 9863.01");
    expect(container.querySelector("[data-final]")?.getAttribute("aria-label")).toBe("AED 9863.01");
  });

  it("a superseded tween settles on its own final value, and completion writes the exact new value", () => {
    controls.complete = false; // tweens stay mid-flight
    const { container, rerender } = render(wrap(100));
    expect(container.textContent).not.toBe("AED 100.00"); // mid-flight interim is allowed while animating
    rerender(wrap(9863.01)); // interrupts: old tween is killed and settled first
    act(() => (controls.lastTween!.vars.onComplete as () => void)()); // the new tween finishes
    expect(container.textContent).toBe("AED 9863.01");
  });

  it("settles on unmount mid-animation (cleanup writes the final value)", () => {
    controls.complete = false;
    const { container, unmount } = render(wrap(1234.5));
    const node = container.querySelector("span")!;
    unmount();
    expect(node.textContent).toBe("AED 1234.50");
  });
});
