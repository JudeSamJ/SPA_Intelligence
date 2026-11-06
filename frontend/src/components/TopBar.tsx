import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { glitchText } from "../motion/effects";
import { useGo } from "../motion/Transition";
import { SunMoon } from "../scenes/SunMoon";
import { usePrefs } from "../state/prefs";
import { Magnetic } from "../motion/Magnetic";

export function TopBar() {
  const { t } = useTranslation();
  const { theme, setTheme, lang, setLang, reduce, setReduce, tier, arabicDigits, setArabicDigits } =
    usePrefs();
  const go = useGo();
  const link = (to: string, label: string) => (
    <NavLink
      to={to}
      end={to === "/"}
      onClick={(e) => {
        e.preventDefault();
        go(to);
      }}
      className={({ isActive }) =>
        `px-3 py-1.5 rounded-full text-sm font-semibold ${isActive ? "bg-surface2 text-fg" : "text-muted hover:text-fg"}`
      }
    >
      {label}
    </NavLink>
  );
  return (
    <header
      className="glass"
      style={{
        position: "fixed",
        top: 10,
        insetInline: 12,
        zIndex: 80,
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "0.45rem 0.9rem",
        borderRadius: 999,
      }}
    >
      <a
        href="/"
        onClick={(e) => {
          e.preventDefault();
          go("/");
        }}
        aria-label={t("brand")}
        style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--fg)", textDecoration: "none" }}
        onMouseEnter={(e) => glitchText(e.currentTarget.querySelector<HTMLElement>("[data-logo]")!, tier)}
      >
        <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="var(--navy)" />
          <path d="M16 4l2 8h-4zM12 12h8l1 16H11z" fill="var(--gold)" />
        </svg>
        <span
          data-logo
          className="display"
          style={{ fontWeight: 700, fontSize: "1.05rem", display: "inline-block" }}
        >
          {t("brand")}
        </span>
      </a>
      <nav aria-label={t("common.mainNav")} style={{ display: "flex", gap: 2, marginInlineStart: 8 }}>
        {link("/", t("nav.home"))}
        {link("/app", t("nav.app"))}
        {link("/app/accuracy", t("nav.accuracy"))}
      </nav>
      <div style={{ flex: 1 }} />
      <button
        className="chip"
        onClick={() => setLang(lang === "en" ? "ar" : "en")}
        aria-label={t("common.language")}
        lang={lang === "en" ? "ar" : "en"}
      >
        {lang === "en" ? "العربية" : "English"}
      </button>
      {lang === "ar" && (
        <label className="chip" style={{ gap: 6 }}>
          <input type="checkbox" checked={arabicDigits} onChange={(e) => setArabicDigits(e.target.checked)} />
          {t("common.digits")}
        </label>
      )}
      <button
        className="chip"
        aria-pressed={reduce}
        onClick={() => setReduce(!reduce)}
        title={t("common.reduceEffects")}
      >
        <span aria-hidden="true">{reduce ? "◔" : "✦"}</span> {t("common.reduceEffects")}
      </button>
      <Magnetic strength={0.25}>
        <button
          className="chip"
          onClick={() => setTheme(theme === "dusk" ? "day" : "dusk")}
          aria-label={theme === "dusk" ? t("common.toDay") : t("common.toDusk")}
          style={{ padding: "0.35rem 0.55rem" }}
        >
          <SunMoon theme={theme} animate={tier !== "reduced"} />
        </button>
      </Magnetic>
    </header>
  );
}
