import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/styles/index.css", "utf8");
const tokens = (theme: string): Record<string, string> => {
  const block = new RegExp(`:root\\[data-theme="${theme}"\\]\\s*\\{([^}]*)\\}`).exec(css)![1]!;
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1]!, m[2]!]),
  );
};
const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
export const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x! + 0.05) / (y! + 0.05);
};

// text-on-surface pairs that actually occur in the UI
const PAIRS: Array<[string, string]> = [
  ["fg", "bg"],
  ["fg", "bg-2"],
  ["fg", "surface"],
  ["fg", "surface-2"],
  ["muted", "bg"],
  ["muted", "surface"],
  ["muted", "surface-2"],
  ["accent", "bg"],
  ["accent", "surface"],
  ["on-accent", "accent-fill"],
  ["danger", "danger-bg"],
  ["fg", "danger-bg"],
  ["ok", "ok-bg"],
  ["fg", "ok-bg"],
  ["fg", "warn-bg"],
  ["gold-ink", "warn-bg"],
  ["info", "bg"],
  ["info", "surface"],
  ["danger", "surface"],
  ["ok", "surface"],
];

describe.each(["day", "dusk"])("WCAG AA contrast (>= 4.5:1) in the %s theme", (theme) => {
  const t = tokens(theme);
  it.each(PAIRS)("%s on %s", (fg, bg) => {
    expect(t[fg], `missing token ${fg}`).toBeTruthy();
    expect(t[bg], `missing token ${bg}`).toBeTruthy();
    expect(ratio(t[fg]!, t[bg]!), `${fg} ${t[fg]} on ${bg} ${t[bg]}`).toBeGreaterThanOrEqual(4.5);
  });
});

describe("landing page (always-dark cinematic palette)", () => {
  const light = "#f3ead3";
  it.each(["#0b1b2b", "#1b2347", "#2a2150", "#3b2250", "#12202f"])("light text on %s", (bg) => {
    expect(ratio(light, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it("secondary text #d6dde3 and gold #f1cf8a on the navy/violet sections", () => {
    for (const bg of ["#0b1b2b", "#1b2347", "#2a2150"]) {
      expect(ratio("#d6dde3", bg)).toBeGreaterThanOrEqual(4.5);
      expect(ratio("#f1cf8a", bg)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
