import { describe, expect, it } from "vitest";
import ar from "./ar.json";
import en from "./en.json";
import { makeFormatters } from "./format";

describe("formatters", () => {
  const f = makeFormatters("en", false, "AED");
  it("formats AED with thousands separators", () => {
    expect(f.aed(9863.01)).toBe("AED 9,863.01");
    expect(f.aed(2450000, 0)).toBe("AED 2,450,000");
  });
  it("formats dates as DD MMM YYYY", () => {
    expect(f.date("2027-06-30")).toBe("30 Jun 2027");
    expect(f.date("2025-03-05")).toBe("05 Mar 2025");
  });
  it("uses Western digits in Arabic by default and Arabic-Indic digits only on opt-in", () => {
    expect(makeFormatters("ar", false, "د.إ").num(1234)).toMatch(/1.234/);
    expect(makeFormatters("ar", true, "د.إ").num(1234)).toContain("١");
    expect(makeFormatters("ar", true, "د.إ").date("2027-06-30")).toMatch(/٣٠/);
  });
  it("trims trailing zeros with flex()", () => {
    expect(f.flex(20)).toBe("20");
    expect(f.flex(12.5)).toBe("12.5");
  });
});

const flat = (o: object, p = ""): string[] =>
  Object.entries(o).flatMap(([k, v]) => (typeof v === "object" && v ? flat(v, `${p}${k}.`) : [`${p}${k}`]));

describe("translations", () => {
  it("English and Arabic have exactly the same keys", () => {
    expect(flat(ar).sort()).toEqual(flat(en).sort());
  });
});
