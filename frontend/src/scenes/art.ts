/** Deterministic generators for original SVG artwork (no external assets, no real brands). */
export function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/** Dune ridge path across width w, resting around `base` with amplitude `amp`. */
export function duneD(seed: number, w: number, h: number, base: number, amp: number, waves = 3): string {
  const r = rng(seed);
  const ph = Array.from({ length: waves }, () => r() * Math.PI * 2);
  const pts: string[] = [];
  const steps = 48;
  for (let i = 0; i <= steps; i++) {
    const x = (i / steps) * w;
    let y = base;
    for (let k = 0; k < waves; k++)
      y += Math.sin((x / w) * Math.PI * (k + 1.3) + (ph[k] ?? 0)) * (amp / (k + 1));
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  return `${pts.join(" ")} L${w} ${h} L0 ${h} Z`;
}

/** Palm Jumeirah-style aerial outline: trunk, crescent, and 16 fronds. Returns path strings. */
export function palmPaths(): { trunk: string; crescent: string; fronds: string[] } {
  const cx = 400,
    cy = 470;
  const trunk = `M${cx} 760 L${cx} ${cy - 150}`;
  const crescent = `M110 330 A 300 300 0 0 1 690 330`;
  const fronds: string[] = [];
  for (let i = 0; i < 8; i++) {
    const y = cy + 160 - i * 38; // up the trunk
    const len = 150 - Math.abs(3.5 - i) * 8;
    const lift = 18 + i * 3;
    fronds.push(`M${cx} ${y} q ${-len * 0.55} ${-lift * 1.8} ${-len} ${lift * 0.4}`);
    fronds.push(`M${cx} ${y} q ${len * 0.55} ${-lift * 1.8} ${len} ${lift * 0.4}`);
  }
  return { trunk, crescent, fronds };
}

/** Burj-style stepped, tapering tower inside generic skyline; coordinates in a 1600x600 viewBox. */
export const TOWER_TIERS: Array<{ w: number; h: number }> = [
  { w: 150, h: 84 },
  { w: 124, h: 84 },
  { w: 98, h: 80 },
  { w: 74, h: 72 },
  { w: 50, h: 62 },
  { w: 30, h: 46 },
];
/** Which of the 4 landing steps lights each tier (index 0 = bottom tier). Step 1 lights the base, step 4 the crown. */
export const BAND_OF_TIER = [0, 0, 1, 2, 3, 3];
export function towerRects(cx: number, baseY: number) {
  let y = baseY;
  return TOWER_TIERS.map((t, i) => {
    y -= t.h;
    return { i, x: cx - t.w / 2, y, w: t.w, h: t.h };
  });
}

/** Generic towers (not real buildings). */
export function genericTowers(
  seed: number,
  count: number,
  w: number,
  minH: number,
  maxH: number,
  skip?: [number, number],
) {
  const r = rng(seed);
  const out: Array<{ x: number; w: number; h: number; roof: number }> = [];
  const slot = w / count;
  for (let i = 0; i < count; i++) {
    const x = i * slot + r() * slot * 0.2;
    if (skip && x > skip[0] && x < skip[1]) continue;
    out.push({ x, w: slot * (0.55 + r() * 0.35), h: minH + r() * (maxH - minH), roof: Math.floor(r() * 3) });
  }
  return out;
}

export function skylineSilhouetteD(
  seed: number,
  w: number,
  base: number,
  minH: number,
  maxH: number,
  towerCx: number,
): string {
  const r = rng(seed);
  const parts = [`M0 ${base}`];
  let x = 0;
  while (x < w) {
    const bw = 40 + r() * 70;
    const near = Math.abs(x - towerCx) < 140;
    const h = near ? minH * 0.5 : minH + r() * (maxH - minH);
    parts.push(`L${x.toFixed(0)} ${(base - h).toFixed(0)} L${(x + bw).toFixed(0)} ${(base - h).toFixed(0)}`);
    x += bw;
  }
  parts.push(`L${w} ${base} Z`);
  return parts.join(" ");
}
