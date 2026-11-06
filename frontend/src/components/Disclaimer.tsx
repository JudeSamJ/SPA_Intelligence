import { useTranslation } from "react-i18next";

/** Visible on every screen (fixed bottom bar). */
export function DisclaimerBar() {
  const { t } = useTranslation();
  return (
    <div
      role="note"
      data-testid="disclaimer"
      style={{
        position: "fixed",
        insetInline: 0,
        bottom: 0,
        zIndex: 85,
        padding: "0.55rem 1rem",
        textAlign: "center",
        background: "var(--surface)",
        color: "var(--fg)",
        borderBlockStart: "1px solid var(--accent)",
        fontSize: "0.9rem",
        fontWeight: 600,
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--accent)", marginInlineEnd: 8 }}>
        ⚖
      </span>
      {t("banner.text")}
    </div>
  );
}
