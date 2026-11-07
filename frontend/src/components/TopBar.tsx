import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation } from "react-router-dom";
import { glitchText } from "../motion/effects";
import { Magnetic } from "../motion/Magnetic";
import { useGo } from "../motion/Transition";
import { SunMoon } from "../scenes/SunMoon";
import { usePrefs } from "../state/prefs";
import { useMedia } from "../state/useMedia";

/**
 * Header. Wide screens: one row (brand, nav, language, effects, theme). Narrow screens (<= 860px): brand + theme
 * toggle + a menu button; the menu panel holds navigation, language, digits and "Reduce effects", so nothing is
 * ever pushed off-screen and every control keeps a >= 44px touch target.
 */
export function TopBar() {
  const { t } = useTranslation();
  const { theme, setTheme, lang, setLang, reduce, setReduce, tier, arabicDigits, setArabicDigits } =
    usePrefs();
  const go = useGo();
  const narrow = useMedia("(max-width: 860px)");
  const [open, setOpen] = useState(false);
  const bar = useRef<HTMLElement>(null);
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname, narrow]);

  // Publish the header's real bottom edge as --inset-top so full-screen scenes can centre in the visible area.
  useEffect(() => {
    const el = bar.current;
    if (!el) return;
    const publish = () =>
      document.documentElement.style.setProperty(
        "--inset-top",
        `${Math.round(el.getBoundingClientRect().bottom)}px`,
      );
    const ro = new ResizeObserver(publish);
    ro.observe(el);
    window.addEventListener("resize", publish);
    publish();
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", publish);
    };
  }, [narrow]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: PointerEvent) => {
      if (bar.current && !bar.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const navLink = (to: string, label: string, big = false) => (
    <NavLink
      key={to}
      to={to}
      end={to === "/"}
      onClick={(e) => {
        e.preventDefault();
        setOpen(false);
        go(to);
      }}
      className={({ isActive }) =>
        `rounded-full font-semibold ${big ? "px-4 py-3 text-base" : "px-3 py-1.5 text-sm"} ${isActive ? "bg-surface2 text-fg" : "text-muted hover:text-fg"}`
      }
      style={big ? { minHeight: 48, display: "flex", alignItems: "center" } : undefined}
    >
      {label}
    </NavLink>
  );

  const langBtn = (
    <button
      className="chip tap"
      onClick={() => setLang(lang === "en" ? "ar" : "en")}
      aria-label={t("common.language")}
      lang={lang === "en" ? "ar" : "en"}
    >
      {lang === "en" ? "العربية" : "English"}
    </button>
  );
  const digitsChk = lang === "ar" && (
    <label className="chip tap" style={{ gap: 6 }}>
      <input type="checkbox" checked={arabicDigits} onChange={(e) => setArabicDigits(e.target.checked)} />
      {t("common.digits")}
    </label>
  );
  const reduceBtn = (
    <button
      className="chip tap"
      aria-pressed={reduce}
      onClick={() => setReduce(!reduce)}
      title={t("common.reduceEffects")}
    >
      <span aria-hidden="true">{reduce ? "◔" : "✦"}</span> {t("common.reduceEffects")}
    </button>
  );
  const themeBtn = (
    <button
      className="chip tap"
      onClick={() => setTheme(theme === "dusk" ? "day" : "dusk")}
      aria-label={theme === "dusk" ? t("common.toDay") : t("common.toDusk")}
      style={{ padding: "0.35rem 0.55rem" }}
    >
      <SunMoon theme={theme} animate={tier !== "reduced"} />
    </button>
  );
  const brand = (
    <a
      href="/"
      onClick={(e) => {
        e.preventDefault();
        go("/");
      }}
      aria-label={t("brand")}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        color: "var(--fg)",
        textDecoration: "none",
        minHeight: 44,
        minWidth: 0,
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget.querySelector<HTMLElement>("[data-logo]");
        if (el) glitchText(el, tier);
      }}
    >
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true" style={{ flex: "none" }}>
        <rect width="32" height="32" rx="8" fill="var(--navy)" />
        <path d="M16 4l2 8h-4zM12 12h8l1 16H11z" fill="var(--gold)" />
      </svg>
      <span
        data-logo
        className="display"
        style={{
          fontWeight: 700,
          fontSize: "1.05rem",
          display: "inline-block",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {t("brand")}
      </span>
    </a>
  );

  return (
    <header
      ref={bar}
      className="glass topbar"
      data-testid="topbar"
      style={{
        position: "fixed",
        top: 10,
        insetInline: 12,
        zIndex: 80,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: narrow ? "0.35rem 0.5rem 0.35rem 0.8rem" : "0.45rem 0.9rem",
        borderRadius: narrow && open ? 22 : 999,
      }}
    >
      {brand}
      {narrow ? (
        <>
          <div style={{ flex: 1 }} />
          <Magnetic strength={0}>{themeBtn}</Magnetic>
          <button
            className="chip tap"
            data-testid="menu-button"
            aria-expanded={open}
            aria-controls="topbar-menu"
            aria-label={open ? t("common.closeMenu") : t("common.menu")}
            onClick={() => setOpen((o) => !o)}
            style={{ padding: "0.35rem 0.7rem", fontSize: "1.15rem", lineHeight: 1 }}
          >
            <span aria-hidden="true">{open ? "✕" : "☰"}</span>
          </button>
          {open && (
            <div
              id="topbar-menu"
              data-testid="menu-panel"
              className="glass"
              style={{
                position: "absolute",
                top: "calc(100% + 8px)",
                insetInline: 0,
                padding: 10,
                display: "grid",
                gap: 6,
                borderRadius: 18,
                background: "var(--surface)",
              }}
            >
              <nav aria-label={t("common.mainNav")} style={{ display: "grid", gap: 2 }}>
                {navLink("/", t("nav.home"), true)}
                {navLink("/app", t("nav.app"), true)}
                {navLink("/app/watch", t("nav.watch"), true)}
                {navLink("/app/crosscheck", t("nav.crosscheck"), true)}
                {navLink("/app/review", t("nav.review"), true)}
                {navLink("/app/accuracy", t("nav.accuracy"), true)}
              </nav>
              <div style={{ height: 1, background: "var(--line)", margin: "4px 0" }} />
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {langBtn}
                {reduceBtn}
                {digitsChk}
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <nav aria-label={t("common.mainNav")} style={{ display: "flex", gap: 2, marginInlineStart: 8 }}>
            {navLink("/", t("nav.home"))}
            {navLink("/app", t("nav.app"))}
            {navLink("/app/watch", t("nav.watch"))}
            {navLink("/app/crosscheck", t("nav.crosscheck"))}
            {navLink("/app/review", t("nav.review"))}
            {navLink("/app/accuracy", t("nav.accuracy"))}
          </nav>
          <div style={{ flex: 1 }} />
          {langBtn}
          {digitsChk}
          {reduceBtn}
          <Magnetic strength={0.25}>{themeBtn}</Magnetic>
        </>
      )}
    </header>
  );
}
