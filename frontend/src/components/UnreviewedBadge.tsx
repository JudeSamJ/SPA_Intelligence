import { useTranslation } from "react-i18next";

/** Shown on every result that depends on a legal-pack entry no lawyer has reviewed. One component, used everywhere. */
export function UnreviewedBadge({ title }: { title?: string }) {
  const { t } = useTranslation();
  return (
    <span
      data-testid="unreviewed-badge"
      className="chip"
      role="note"
      title={title ?? t("badge.unreviewedHelp")}
      style={{
        cursor: "help",
        borderColor: "var(--warn)",
        color: "var(--warn)",
        background: "var(--warn-bg)",
        fontWeight: 700,
        whiteSpace: "nowrap",
      }}
    >
      ⚖ {t("badge.unreviewed")}
    </span>
  );
}
