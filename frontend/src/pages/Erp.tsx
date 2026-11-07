import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiX, type ErpResult } from "../api/trust";
import { UnreviewedBadge } from "../components/UnreviewedBadge";
import { Alert } from "../components/ui";
import { useFmt } from "../i18n/format";
import { useContractCtx } from "./ctx";

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Erp() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, detail } = useContractCtx();
  const [days, setDays] = useState(90);
  const [asOf, setAsOf] = useState(detail.contract.handover_date.value ?? new Date().toISOString().slice(0, 10));
  const [confirm, setConfirm] = useState(false);
  const dlg = useRef<HTMLDialogElement>(null);
  const ex = useMutation({ mutationFn: () => apiX.erpExport(id, { delay_days: days, as_of_date: asOf }) });
  const push = useMutation({ mutationFn: () => apiX.erpPush(id, { delay_days: days, as_of_date: asOf, confirm: true, reviewer: "ui" }) });
  const r: ErpResult | undefined = ex.data;
  const cols = r?.rows[0] ? Object.keys(r.rows[0]) : [];
  const th = { textAlign: "start" as const, padding: "0.5rem 0.7rem", fontSize: "0.8rem", color: "var(--muted)", whiteSpace: "nowrap" as const };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)" };
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }}>
        <h2 className="display" style={{ margin: 0, fontSize: "1.3rem" }}>{t("erp.title")}</h2>
        <Alert tone="warn"><span data-testid="erp-placeholder">{t("erp.placeholder")}</span></Alert>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
          <label style={{ display: "grid", gap: 4 }}>{t("gap.delayDays")}
            <input type="number" min={0} max={3650} value={days} onChange={(e) => setDays(Math.max(0, Number(e.target.value) || 0))} style={{ minHeight: 44, width: 120 }} /></label>
          <label style={{ display: "grid", gap: 4 }}>{t("gap.asOf")}
            <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ minHeight: 44 }} /></label>
          <button className="btn" onClick={() => ex.mutate()} disabled={ex.isPending} data-testid="erp-preview">{t("erp.preview")}</button>
        </div>
        {ex.error && <Alert tone="danger">{(ex.error as Error).message}</Alert>}
      </section>

      {r && (
        <>
          <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <strong>{t("erp.entity")}: <code>{r.entity}</code></strong>
              <span className="chip">{t("erp.mode")}: {r.mode}</span>
              <span className="chip num" data-testid="erp-count">{t("erp.rows", { n: r.row_count })}</span>
              <span className="chip" style={{ color: r.valid ? "var(--ok)" : "var(--danger)", borderColor: r.valid ? "var(--ok)" : "var(--danger)" }} data-testid="erp-valid">{r.valid ? t("erp.valid") : t("erp.invalid", { n: r.errors.length })}</span>
              <UnreviewedBadge title={t("erp.exposureHelp")} />
            </div>
            <p style={{ margin: 0, color: "var(--muted)" }}>{r.mapping_note}</p>
            {r.errors.length > 0 && (
              <ul data-testid="erp-errors" style={{ margin: 0, paddingInlineStart: "1.2rem" }}>
                {r.errors.map((e, i) => <li key={i}>{t("erp.row")} {e.row}: <code>{e.field}</code> {e.error}</li>)}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn btn-ghost" onClick={() => download(`erp_${id.slice(0, 8)}.csv`, r.csv, "text/csv")} data-testid="erp-csv">{t("erp.downloadCsv")}</button>
              <button className="btn btn-ghost" onClick={() => download(`erp_${id.slice(0, 8)}.json`, JSON.stringify(r.rows, null, 2), "application/json")}>{t("erp.downloadJson")}</button>
              <button className="btn" disabled={!r.valid} onClick={() => dlg.current?.showModal()} data-testid="erp-push">{t("erp.push")}</button>
            </div>
            {!r.push_enabled && <p style={{ margin: 0, color: "var(--muted)" }}>{t("erp.pushDisabled")}</p>}
          </section>

          <section className="card" style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 760 }} data-testid="erp-table">
              <thead><tr>{cols.map((c) => <th key={c} style={th}>{c}</th>)}</tr></thead>
              <tbody>
                {r.rows.map((row, i) => (
                  <tr key={i}>{cols.map((c) => <td key={c} style={td} className="num" dir="auto">{typeof row[c] === "number" && c.toLowerCase().includes("amount") ? fmt.flex(row[c] as number) : String(row[c] ?? "–")}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      <dialog ref={dlg} aria-labelledby="erp-dlg-h" style={{ borderRadius: 12, border: "1px solid var(--line)", background: "var(--surface)", color: "var(--fg)", maxWidth: 480, padding: "1.2rem" }} data-testid="erp-dialog">
        <h3 id="erp-dlg-h" className="display" style={{ marginTop: 0 }}>{t("erp.confirmTitle")}</h3>
        <p>{t("erp.confirmBody", { n: r?.row_count ?? 0 })}</p>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="erp-confirm-check" style={{ width: 22, height: 22 }} /> {t("erp.confirmCheck")}
        </label>
        {push.error && <Alert tone="danger"><span data-testid="erp-push-error">{(push.error as Error).message}</span></Alert>}
        {push.data && <Alert tone="ok">{t("erp.pushed", { n: push.data.pushed })}</Alert>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginBlockStart: 12 }}>
          <button className="btn btn-ghost" onClick={() => { setConfirm(false); dlg.current?.close(); }}>{t("erp.cancel")}</button>
          <button className="btn" disabled={!confirm || push.isPending} onClick={() => push.mutate()} data-testid="erp-confirm-push">{t("erp.confirmPush")}</button>
        </div>
      </dialog>
    </div>
  );
}
