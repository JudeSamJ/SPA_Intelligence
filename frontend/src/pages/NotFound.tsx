import { useTranslation } from "react-i18next";
import { useGo } from "../motion/Transition";

export default function NotFound() {
  const { t } = useTranslation();
  const go = useGo();
  return (
    <section style={{ padding: "9rem 1.5rem 4rem", textAlign: "center" }}>
      <h1 data-glitch-title className="display" style={{ fontSize: "3rem" }}>
        {t("errors.notFoundTitle")}
      </h1>
      <p style={{ color: "var(--muted)" }}>{t("errors.notFoundBody")}</p>
      <button className="btn" onClick={() => go("/")}>
        {t("common.home")}
      </button>
    </section>
  );
}
