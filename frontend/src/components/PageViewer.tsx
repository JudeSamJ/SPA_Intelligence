import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Evidence } from "../api/trust";
import { useAuthedSrc } from "../auth/useAuthedSrc";
import { gsap } from "../motion/registry";
import { usePrefs } from "../state/prefs";

/**
 * A rendered PDF page (server-side PNG) with the evidence rectangles drawn as an overlay.
 * Rect coordinates are PDF points, so they are placed in percent of the page size: exact at any zoom.
 */
export function PageViewer({
  src,
  page,
  evidence,
  height = 520,
  label,
}: {
  src: string;
  page: number;
  evidence?: Evidence | null;
  height?: number | string;
  label: string;
}) {
  const { t } = useTranslation();
  const { tier } = usePrefs();
  const shown = useAuthedSrc(src);
  const box = useRef<HTMLDivElement>(null);
  const [loadedSrc, setLoadedSrc] = useState("");
  const loaded = loadedSrc === src;
  const rects = useMemo(() => (evidence && evidence.page === page ? evidence.rects : []), [evidence, page]);
  const W = evidence?.page_width ?? 0;
  const H = evidence?.page_height ?? 0;

  // scroll the first highlight into view and let it pulse once (entrance only, never on the text itself)
  useEffect(() => {
    if (!loaded || !box.current || !rects.length || !W || !H) return;
    const el = box.current;
    const img = el.querySelector("img");
    if (img && typeof el.scrollTo === "function") el.scrollTo({ top: Math.max(0, ((rects[0]?.[1] ?? 0) / H) * img.clientHeight - 70), behavior: tier === "reduced" ? "auto" : "smooth" });
    if (tier === "reduced") return;
    const tw = gsap.fromTo(
      el.querySelectorAll("[data-highlight]"),
      { opacity: 0.05, scale: 1.06 },
      { opacity: 1, scale: 1, duration: 0.55, ease: "power2.out", clearProps: "scale" },
    );
    return () => void tw.kill();
  }, [loaded, rects, W, H, tier]);

  return (
    <div ref={box} data-testid="page-viewer" style={{ overflow: "auto", height, background: "#fff", borderRadius: 8 }}>
      <div style={{ position: "relative", width: "100%" }}>
        {shown && <img
          key={src}
          src={shown}
          alt={label}
          ref={(el) => {
            if (el?.complete && el.naturalWidth > 0) setLoadedSrc(src); // cached image: load may fire before React attaches
          }}
          onLoad={() => setLoadedSrc(src)}
          style={{ display: "block", width: "100%", height: "auto" }}
        />}
        {loaded &&
          W > 0 &&
          rects.map((r, i) => {
            const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = r;
            return (
            <div
              key={i}
              data-highlight
              data-testid="highlight"
              aria-label={t("evidence.highlighted")}
              style={{
                position: "absolute",
                left: `${(x0 / W) * 100}%`,
                top: `${(y0 / H) * 100}%`,
                width: `${((x1 - x0) / W) * 100}%`,
                height: `${((y1 - y0) / H) * 100}%`,
                background: "color-mix(in srgb, #ffd23f 55%, transparent)",
                outline: "2px solid #e8a200",
                borderRadius: 3,
                mixBlendMode: "multiply",
                pointerEvents: "none",
              }}
            />
            );
          })}
      </div>
    </div>
  );
}
