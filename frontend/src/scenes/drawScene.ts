import { duneD, rng, skylineSilhouetteD, towerRects } from "./art";

export type SceneTheme = "day" | "dusk";

/** Parse the SVG path produced by duneD (M/L/Z only) and fill it on a 2D canvas. */
function fillPath(ctx: CanvasRenderingContext2D, d: string, fill: string | CanvasGradient) {
  const p = new Path2D(d);
  ctx.fillStyle = fill;
  ctx.fill(p);
}

/**
 * Procedural golden-hour scene: sky, sun, far skyline with one stepped tower, far dunes. Original artwork.
 * It is the "image" the WebGL glitch shader distorts, and the static fallback when WebGL is not used.
 */
export function drawSunsetScene(canvas: HTMLCanvasElement, theme: SceneTheme) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width,
    h = canvas.height;
  const sky = ctx.createLinearGradient(0, 0, 0, h);
  const stops =
    theme === "dusk"
      ? [
          [0, "#0b1b2b"],
          [0.38, "#2a2150"],
          [0.66, "#8a3f4a"],
          [0.86, "#d98a4b"],
          [1, "#f3c46a"],
        ]
      : [
          [0, "#2d2a5a"],
          [0.4, "#7d4468"],
          [0.7, "#e0884f"],
          [0.9, "#f6c56a"],
          [1, "#ffe7a8"],
        ];
  stops.forEach(([o, c]) => sky.addColorStop(o as number, c as string));
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);

  const sun = ctx.createRadialGradient(w * 0.5, h * 0.7, 0, w * 0.5, h * 0.7, h * 0.55);
  sun.addColorStop(0, "rgba(255,236,170,0.95)");
  sun.addColorStop(0.18, "rgba(255,200,120,0.55)");
  sun.addColorStop(1, "rgba(255,160,90,0)");
  ctx.fillStyle = sun;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "rgba(255,244,205,0.95)";
  ctx.beginPath();
  ctx.arc(w * 0.5, h * 0.7, h * 0.06, 0, Math.PI * 2);
  ctx.fill();

  // far skyline (reuse the SVG generators, scaled to canvas)
  const sc = w / 1600;
  ctx.save();
  ctx.scale(sc, sc);
  const base = (h / sc) * 0.78;
  fillPath(ctx, skylineSilhouetteD(3, 1600, base, 70, 230, 1050), "rgba(38,24,52,0.78)");
  const r = rng(9);
  for (let x = 20; x < 1600; x += 70 + r() * 40) {
    if (Math.abs(x - 1050) < 110) continue;
    const bh = 90 + r() * 210,
      bw = 34 + r() * 36;
    ctx.fillStyle = "rgba(30,18,44,0.86)";
    ctx.fillRect(x, base - bh, bw, bh);
  }
  ctx.fillStyle = "rgba(24,14,36,0.95)";
  towerRects(1050, base).forEach((t) => ctx.fillRect(t.x, t.y, t.w, t.h + 1));
  ctx.fillRect(1048, towerRects(1050, base).at(-1)!.y - 120, 4, 124);
  fillPath(ctx, duneD(21, 1600, h / sc, base - 10, 36, 3), "rgba(90,40,60,0.9)");
  fillPath(ctx, duneD(33, 1600, h / sc, base + 40, 50, 3), "rgba(60,26,44,0.95)");
  ctx.restore();
}
