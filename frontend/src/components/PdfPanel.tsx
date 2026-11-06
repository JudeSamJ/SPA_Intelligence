import { useTranslation } from "react-i18next";
import { api } from "../api/client";

/** Lazy-loaded PDF viewer (browser PDF viewer in an iframe, opened at a page). Re-mounts per page for reliability. */
export default function PdfPanel({ id, page, onClose }: { id: string; page: number; onClose: () => void }) {
  const { t } = useTranslation();
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
        gridTemplateRows: "auto 1fr",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "0.5rem 0.8rem",
          borderBlockEnd: "1px solid var(--line)",
        }}
      >
        <strong style={{ flex: 1 }}>
          {t("terms.pdfTitle")} ·{" "}
          <span className="num">
            {t("common.page")} {page}
          </span>
        </strong>
        <button className="chip" onClick={onClose}>
          {t("terms.closePdf")}
        </button>
      </div>
      <iframe
        key={page}
        title={`${t("terms.pdfTitle")} ${t("common.page")} ${page}`}
        src={api.pdfUrl(id, page)}
        style={{ width: "100%", height: "100%", border: 0, background: "#fff" }}
      />
    </aside>
  );
}
