import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { apiX, type Obligation } from "../api/trust";
import { EvidenceLink } from "../components/EvidenceLink";
import { ObligationCalendar } from "../components/ObligationCalendar";
import { ObligationTimeline } from "../components/ObligationTimeline";
import { Alert, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { useContractCtx } from "./ctx";

const SEV_COLOR: Record<string, string> = { high: "var(--danger)", medium: "var(--warn)", low: "var(--info)", none: "var(--muted)" };

/** Shared by the global Watch page (all contracts) and the per-contract Obligations tab. */
export function ObligationsView({ contractId }: { contractId?: string }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const qc = useQueryClient();
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [within, setWithin] = useState<number | "all">("all");
  const [status, setStatus] = useState("");
  const q = useQuery({
    queryKey: ["obl", asOf, within, status, contractId],
    queryFn: () => apiX.obligations({ as_of: asOf, within_days: within === "all" ? undefined : within, status: status || undefined, contract_id: contractId }),
    placeholderData: keepPreviousData,
  });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => apiX.alerts(false) });
  const recompute = useMutation({ mutationFn: () => apiX.recompute(asOf), onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }) });
  const ack = useMutation({ mutationFn: (id: string) => apiX.ack(id), onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }) });
  const rows = q.data?.obligations ?? [];
  const feed = (alerts.data?.alerts ?? []).filter((a) => !contractId || a.contract_id === contractId);
  const th = { textAlign: "start" as const, padding: "0.5rem 0.7rem", fontSize: "0.85rem", color: "var(--muted)" };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)", verticalAlign: "top" as const };
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }}>
        <h2 className="display" style={{ margin: 0, fontSize: "1.3rem" }}>{contractId ? t("obl.titleContract") : t("obl.titleAll")}</h2>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("obl.intro")}</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
          <label style={{ display: "grid", gap: 4 }}>{t("obl.asOf")}
            <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ minHeight: 44 }} data-testid="obl-asof" /></label>
          <label style={{ display: "grid", gap: 4 }}>{t("obl.within")}
            <select value={String(within)} onChange={(e) => setWithin(e.target.value === "all" ? "all" : Number(e.target.value))} style={{ minHeight: 44 }} data-testid="obl-within">
              <option value="all">{t("obl.all")}</option>
              {[30, 90, 180, 365].map((d) => <option key={d} value={d}>{t("obl.nDays", { n: d })}</option>)}
            </select></label>
          <label style={{ display: "grid", gap: 4 }}>{t("obl.eventFilter")}
            <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ minHeight: 44 }} data-testid="obl-status">
              <option value="">{t("obl.all")}</option>
              {(q.data?.event_types ?? []).map((s) => <option key={s} value={s}>{t(`obl.events.${s}`)}</option>)}
            </select></label>
          <button className="btn btn-ghost" onClick={() => recompute.mutate()} disabled={recompute.isPending}>{t("obl.recompute")}</button>
        </div>
        {q.data && <Alert tone="info">{q.data.caveat}</Alert>}
      </section>

      <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }} aria-labelledby="alerts-h">
        <h3 id="alerts-h" className="display" style={{ margin: 0, fontSize: "1.1rem" }}>{t("obl.alerts")} <span className="num" data-testid="alerts-count">({feed.length})</span></h3>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("obl.inAppOnly")}</p>
        {feed.length === 0 ? <span>{t("obl.noAlerts")}</span> : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
            {feed.map((a) => (
              <li key={a.id} data-testid="alert" className="card" style={{ padding: "0.6rem 0.8rem", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", borderInlineStart: `4px solid ${SEV_COLOR[a.severity]}` }}>
                <strong style={{ color: SEV_COLOR[a.severity] }}>{t(`gap.severity.${a.severity}`)}</strong>
                <span style={{ flex: 1, minWidth: 200 }} dir="auto">{!contractId && <em>{a.contract_name}: </em>}{a.message}</span>
                <button className="chip" onClick={() => ack.mutate(a.id)} data-testid="ack">{t("obl.ack")}</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {q.isLoading && <Skeleton h={200} />}
      {q.error && <ErrorState title={t("errors.generic")} message={(q.error as Error).message} onRetry={() => void q.refetch()} />}
      {q.data && rows.length === 0 && <EmptyState title={t("obl.none")} body={t("obl.noneBody")} />}
      {rows.length > 0 && (
        <>
          <section className="card" style={{ padding: "0.8rem 1rem" }}><ObligationTimeline rows={rows} asOf={q.data!.as_of} /></section>
          {contractId && <ObligationCalendar rows={rows} asOf={q.data!.as_of} />}
          <section className="card" style={{ overflowX: "auto" }}>
            <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }} data-testid="obl-table">
              <thead><tr>
                {!contractId && <th style={th}>{t("obl.contract")}</th>}
                <th style={th}>{t("obl.obligation")}</th><th style={th}>{t("obl.due")}</th><th style={th}>{t("obl.in")}</th><th style={th}>{t("obl.event")}</th><th style={th}>{t("evidence.title")}</th>
              </tr></thead>
              <tbody>
                {rows.map((o: Obligation) => (
                  <tr key={o.id} data-testid="obl-row" data-event={o.event_type ?? ""}>
                    {!contractId && <td style={td} data-label={t("obl.contract")} dir="auto"><Link to={`/app/contracts/${o.contract_id}/obligations`}>{o.contract_name}</Link></td>}
                    <th scope="row" style={{ ...td, textAlign: "start", fontWeight: 600 }} dir="auto">
                      {o.label}{o.amount != null && <span className="num"> · {fmt.aed(o.amount, 0)}</span>}
                      {o.assumed_anchor && <div style={{ color: "var(--muted)", fontWeight: 400, fontSize: "0.82rem" }}>{o.assumed_anchor}</div>}
                    </th>
                    <td style={td} className="num" data-label={t("obl.due")}>{fmt.date(o.due_date)}</td>
                    <td style={td} className="num" data-label={t("obl.in")}>{o.days_until < 0 ? t("obl.daysAgo", { n: fmt.num(-o.days_until) }) : t("obl.nDays", { n: fmt.num(o.days_until) })}</td>
                    <td style={td} data-label={t("obl.event")}>
                      <span className="chip" style={{ borderColor: SEV_COLOR[o.severity], color: SEV_COLOR[o.severity] }}>{o.event_type ? t(`obl.events.${o.event_type}`) : t(`obl.status.${o.status}`)}</span>
                    </td>
                    <td style={td} data-label={t("evidence.title")}>
                      {contractId ? <EvidenceLink field={o.field} page={o.evidence.page} quote={o.evidence.quote} />
                        : <Link className="chip num" to={`/app/contracts/${o.contract_id}/terms`}>{t("common.pageShort")} {o.evidence.page ?? "–"}</Link>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

export default function Obligations() {
  const { id } = useContractCtx();
  return <ObligationsView contractId={id} />;
}
