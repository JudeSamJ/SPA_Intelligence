import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { apiX } from "../api/trust";
import { PageViewer } from "./PageViewer";
import type { EvidenceTarget } from "../pages/ctx";

/** Side panel: the real page image with the exact span highlighted. Opens for a field, or for any page + quote. */
export default function PdfPanel({
  id,
  target,
  pages,
  onClose,
}: {
  id: string;
  target: EvidenceTarget;
  pages: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const byField = useQuery({
    queryKey: ["evidence", id, target.field],
    queryFn: () => apiX.evidence(id, target.field!),
    enabled: !!target.field,
    retry: false,
  });
  const byQuote = useQuery({
    queryKey: ["locate", id, target.page, target.quote],
    queryFn: () => apiX.locate(id, target.page!, target.quote!),
    enabled: !target.field && !!target.page && !!target.quote,
    retry: false,
  });
  const ev = target.field ? byField.data?.evidence : byQuote.data;
  const startPage = ev?.page ?? target.page ?? 1;
  const [manual, setManual] = useState<{ key: string; page: number } | null>(null);
  const key = `${target.field ?? ""}|${target.page ?? ""}|${target.quote ?? ""}`;
  const page = manual && manual.key === key ? manual.page : startPage;
  const found = !!ev?.rects?.length;
  return (
    <aside
      id="pdf-panel"
      className="card"
      aria-label={t("terms.pdfTitle")}
      style={{
        position: "sticky",
        top: "5rem",
        height: "calc(100dvh - 8.5rem)",
        display: "grid",
        gridTemplateRows: "auto auto 1fr",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0.5rem 0.8rem", borderBlockEnd: "1px solid var(--line)" }}>
        <strong style={{ flex: 1 }}>
          {t("terms.pdfTitle")} · <span className="num">{t("common.page")} {page}/{pages}</span>
        </strong>
        <button className="chip" aria-label={t("evidence.prev")} disabled={page <= 1} onClick={() => setManual({ key, page: page - 1 })}>‹</button>
        <button className="chip" aria-label={t("evidence.next")} disabled={page >= pages} onClick={() => setManual({ key, page: page + 1 })}>›</button>
        <a className="chip" href={api.pdfUrl(id, page)} target="_blank" rel="noreferrer">{t("evidence.openPdf")}</a>
        <button className="chip" onClick={onClose}>{t("terms.closePdf")}</button>
      </div>
      <p role="status" style={{ margin: 0, padding: "0.35rem 0.8rem", fontSize: "0.85rem", color: found ? "var(--ok)" : "var(--muted)" }}>
        {byField.isLoading || byQuote.isLoading
          ? t("common.loading")
          : found
            ? t("evidence.highlighted")
            : t("evidence.noBox")}
      </p>
      <PageViewer src={apiX.pageUrl(id, page, 1.6)} page={page} evidence={ev} height="100%" label={`${t("terms.pdfTitle")} ${t("common.page")} ${page}`} />
    </aside>
  );
}
