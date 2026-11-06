import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "./en.json";

const walk = (d: string): string[] =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith(".tsx") || p.endsWith(".ts") ? [p] : [];
  });
const has = (k: string) =>
  k.split(".").reduce<unknown>((o, p) => (o as Record<string, unknown> | undefined)?.[p], en as unknown) !==
  undefined;

describe("i18n keys used in source", () => {
  it("every literal t('...') key exists in en.json (plural keys allowed via _one/_other)", () => {
    const missing: string[] = [];
    for (const file of walk("src").filter((f) => !f.includes(".test."))) {
      for (const m of readFileSync(file, "utf8").matchAll(/\bt\(\s*["'`]([a-zA-Z0-9_.]+)["'`]/g)) {
        const k = m[1]!;
        if (!has(k) && !has(`${k}_one`)) missing.push(`${file}: ${k}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
