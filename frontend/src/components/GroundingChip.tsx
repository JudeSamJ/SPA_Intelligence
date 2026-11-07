import { useTranslation } from "react-i18next";
import { useFmt } from "../i18n/format";

interface Item {
  grounding?: { status: string } | null;
  confidence?: number | null;
  needs_review?: boolean;
  human_verified?: boolean;
}

/** grounded | partial | ungrounded | human verified, with the confidence score. */
export function GroundingChip({ item }: { item: Item }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const s = item.human_verified ? "human" : (item.grounding?.status ?? "not_stated");
  const tone =
    s === "grounded" || s === "human"
      ? "var(--ok)"
      : s === "partial"
        ? "var(--warn)"
        : s === "ungrounded"
          ? "var(--danger)"
          : "var(--muted)";
  return (
    <span
      data-testid="grounding-chip"
      data-status={s}
      className="chip"
      style={{ borderColor: tone, color: tone, whiteSpace: "nowrap", fontSize: "0.78rem" }}
      title={t("evidence.confidenceHelp")}
    >
      {t(`evidence.status.${s}`)}
      {item.confidence != null && s !== "not_stated" && s !== "human" ? ` · ${fmt.pct(item.confidence * 100, 0)}` : ""}
    </span>
  );
}
