import { useTranslation } from "react-i18next";
import { useContractCtx } from "../pages/ctx";

/** A small "p. N" button that opens the PDF panel with the exact span highlighted. */
export function EvidenceLink({ field, page, quote }: { field?: string; page?: number | null; quote?: string | null }) {
  const { t } = useTranslation();
  const { openEvidence } = useContractCtx();
  if (!page && !field) return <span>–</span>;
  return (
    <button
      className="chip num"
      data-testid="evidence-link"
      title={quote ?? undefined}
      aria-label={t("terms.openAtPage", { page: page ?? "" })}
      onClick={() => openEvidence({ field, page: page ?? undefined, quote })}
    >
      {page ? `${t("common.pageShort")} ${page}` : t("evidence.open")}
    </button>
  );
}
