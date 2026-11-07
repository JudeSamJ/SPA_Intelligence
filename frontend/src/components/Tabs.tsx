import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation } from "react-router-dom";
import { Flip } from "../motion/registry";
import { usePrefs } from "../state/prefs";

const TABS = ["terms", "gap", "penalty", "cashflow", "obligations", "playbook", "erp", "assistant"] as const;

/** Tabs by URL. The highlight pill glides between tabs with Flip.fit. */
export function Tabs({ base }: { base: string }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const { tier, dir } = usePrefs();
  const wrap = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const first = useRef(true);
  const active = TABS.find((k) => pathname.includes(`/${k}`)) ?? "terms";

  useEffect(() => {
    const el = wrap.current?.querySelector<HTMLElement>(`[data-tab="${active}"]`);
    if (!el || !pill.current) return;
    const instant = first.current || tier === "reduced";
    first.current = false;
    Flip.fit(pill.current, el, {
      duration: instant ? 0 : 0.45,
      ease: "power3.out",
      scale: false,
      absolute: true,
    });
  }, [active, tier, dir]);

  useEffect(() => {
    const onResize = () => {
      const el = wrap.current?.querySelector<HTMLElement>(`[data-tab="${active}"]`);
      if (el && pill.current) Flip.fit(pill.current, el, { duration: 0, scale: false, absolute: true });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [active]);

  return (
    <div ref={wrap} role="tablist" aria-label={t("shell.tabs")} className="tabs">
      <span
        ref={pill}
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          borderRadius: 999,
          background: "var(--accent-fill)",
          pointerEvents: "none",
        }}
      />
      {TABS.map((k) => (
        <NavLink
          key={k}
          data-tab={k}
          to={`${base}/${k}`}
          role="tab"
          aria-selected={active === k}
          style={{ color: active === k ? "var(--on-accent)" : "var(--fg)" }}
        >
          {t(`tabs.${k}`)}
        </NavLink>
      ))}
    </div>
  );
}
