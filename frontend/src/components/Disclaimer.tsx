import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

const KEY = "spa.banner";
const read = () => {
  try {
    return localStorage.getItem(KEY) === "hidden";
  } catch {
    return false;
  }
};

/**
 * "Decision support, not legal advice." Shown by default on every screen. The user can dismiss it; a small
 * scales tab stays in the corner so it is always one click away. The choice is remembered.
 */
export function DisclaimerBar() {
  const { t } = useTranslation();
  const [hidden, setHidden] = useState(read);

  useEffect(() => {
    document.documentElement.dataset.banner = hidden ? "hidden" : "shown";
    try {
      localStorage.setItem(KEY, hidden ? "hidden" : "shown");
    } catch {
      /* storage blocked: just not remembered */
    }
  }, [hidden]);

  if (hidden) {
    return (
      <button
        data-testid="disclaimer-show"
        aria-label={t("banner.show")}
        title={t("banner.show")}
        onClick={() => setHidden(false)}
        className="chip"
        style={{
          position: "fixed",
          bottom: 12,
          insetInlineStart: 12,
          zIndex: 85,
          padding: "0.45rem 0.7rem",
          background: "var(--surface)",
        }}
      >
        <span aria-hidden="true" style={{ color: "var(--accent)" }}>
          ⚖
        </span>
      </button>
    );
  }
  return (
    <div
      role="note"
      data-testid="disclaimer"
      style={{
        position: "fixed",
        insetInline: 0,
        bottom: 0,
        zIndex: 85,
        padding: "0.55rem 3.4rem calc(0.55rem + env(safe-area-inset-bottom, 0px))",
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
      <button
        data-testid="disclaimer-dismiss"
        className="banner-x"
        aria-label={t("banner.dismiss")}
        title={t("banner.dismiss")}
        onClick={() => setHidden(true)}
        style={{
          position: "absolute",
          insetInlineEnd: 10,
          top: "50%",
          transform: "translateY(-50%)",
          width: 36,
          height: 36,
          borderRadius: "50%",
          border: "1px solid var(--line)",
          background: "transparent",
          color: "var(--fg)",
          cursor: "pointer",
          fontSize: "1.1rem",
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}
