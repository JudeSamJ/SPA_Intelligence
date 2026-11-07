import { useMutation } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiX, type MCRequest, type MCResult, type Summary } from "../api/trust";
import { Alert, Skeleton } from "./ui";
import { UnreviewedBadge } from "./UnreviewedBadge";
import { useFmt } from "../i18n/format";
import { useContractCtx } from "../pages/ctx";
import { useQuery } from "@tanstack/react-query";

const McChart = lazy(() => import("./McChart"));
const FAMILIES = { triangular: ["min_days", "mode_days", "max_days"], lognormal: ["median_days", "sigma"], fixed: ["days"] } as const;

function Row({ label, s, badge }: { label: string; s: Summary | null; badge?: boolean }) {
  const fmt = useFmt();
  return (
    <tr>
      <th scope="row" style={{ textAlign: "start", padding: "0.5rem 0.7rem", fontWeight: 600 }}>{label} {badge && <UnreviewedBadge />}</th>
      {s ? ([s.p10, s.p50, s.p90] as number[]).map((v, i) => <td key={i} className="num" data-label={["P10", "P50", "P90"][i]} style={{ padding: "0.5rem 0.7rem" }}>{fmt.aed(v, 2)}</td>) : <td colSpan={3} style={{ padding: "0.5rem 0.7rem", color: "var(--muted)" }}>–</td>}
    </tr>
  );
}

/** Probabilistic view of the penalty. ASSUMPTION-DRIVEN: the delay distribution is an input, not a forecast. */
export function Probabilistic() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, detail } = useContractCtx();
  const defaults = useQuery({ queryKey: ["mcdef"], queryFn: apiX.mcDefaults, staleTime: Infinity });
  const [family, setFamily] = useState<"triangular" | "lognormal" | "fixed">("triangular");
  const [params, setParams] = useState<Record<string, number>>({});
  const [trials, setTrials] = useState(10000);
  const [seed, setSeed] = useState(42);
  const [asOf, setAsOf] = useState(detail.contract.handover_date.value ?? new Date().toISOString().slice(0, 10));
  const [csv, setCsv] = useState("");
  const [showPortfolio, setShowPortfolio] = useState(false);
  useEffect(() => {
    const d = defaults.data?.delay_distribution;
    if (d?.family) {
      setFamily(d.family as typeof family);
      setParams(Object.assign({}, ...Object.values(FAMILIES).flat().map((k) => (k in (d[d.family] ?? {}) ? { [k]: d[d.family]?.[k] } : {}))));
    }
  }, [defaults.data]);
  const body = (): MCRequest => ({ family, params: Object.fromEntries(FAMILIES[family].map((k) => [k, Number(params[k] ?? defaults.data?.delay_distribution?.[family]?.[k] ?? 0)])), trials, seed, as_of_date: asOf, signal_csv: csv.trim() || undefined });
  const run = useMutation({ mutationFn: () => apiX.mc(id, body()) });
  const port = useMutation({ mutationFn: () => apiX.mcPortfolio(body()) });
  const r: MCResult | undefined = run.data;
  useEffect(() => { if (defaults.data?.delay_distribution && !run.data && !run.isPending) run.mutate(); }, [defaults.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const dp = (k: string) => params[k] ?? defaults.data?.delay_distribution?.[family]?.[k] ?? "";
  const th = { textAlign: "start" as const, padding: "0.5rem 0.7rem", fontSize: "0.85rem", color: "var(--muted)" };
  return (
    <section className="card" style={{ padding: "1rem", display: "grid", gap: 14 }} aria-labelledby="mc-h" data-testid="mc">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <h2 id="mc-h" className="display" style={{ margin: 0, fontSize: "1.3rem", flex: 1 }}>{t("mc.title")}</h2>
        <span className="chip" data-testid="mc-assumption" style={{ borderColor: "var(--warn)", color: "var(--warn)", fontWeight: 700 }}>{t("mc.assumptionDriven")}</span>
      </div>
      <Alert tone="info">{t("mc.disclaimer")}</Alert>
      <fieldset style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "0.8rem", display: "flex", flexWrap: "wrap", gap: 12 }}>
        <legend style={{ padding: "0 6px", fontWeight: 700 }}>{t("mc.assumptions")}</legend>
        <label style={{ display: "grid", gap: 4 }}>{t("mc.family")}
          <select value={family} onChange={(e) => { setFamily(e.target.value as typeof family); setParams({}); }} style={{ minHeight: 44 }} data-testid="mc-family">
            {Object.keys(FAMILIES).map((f) => <option key={f} value={f}>{t(`mc.families.${f}`)}</option>)}
          </select></label>
        {FAMILIES[family].map((k) => (
          <label key={k} style={{ display: "grid", gap: 4 }}>{t(`mc.params.${k}`)}
            <input type="number" step="any" value={dp(k)} onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })} style={{ minHeight: 44, width: 110 }} data-testid={`mc-${k}`} /></label>
        ))}
        <label style={{ display: "grid", gap: 4 }}>{t("mc.trials")}<input type="number" min={100} max={50000} value={trials} onChange={(e) => setTrials(Number(e.target.value) || 1000)} style={{ minHeight: 44, width: 110 }} /></label>
        <label style={{ display: "grid", gap: 4 }}>{t("mc.seed")}<input type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} style={{ minHeight: 44, width: 90 }} /></label>
        <label style={{ display: "grid", gap: 4 }}>{t("gap.asOf")}<input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ minHeight: 44 }} /></label>
        <label style={{ display: "grid", gap: 4, flex: "1 1 280px" }}>{t("mc.signal")}
          <textarea rows={3} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder="date,planned_progress_pct,actual_progress_pct&#10;2026-06-01,60,50" style={{ fontFamily: "monospace" }} /></label>
        <button className="btn" onClick={() => run.mutate()} disabled={run.isPending} data-testid="mc-run">{run.isPending ? t("mc.running") : t("mc.rerun")}</button>
      </fieldset>
      {run.error && <Alert tone="danger">{(run.error as Error).message}</Alert>}
      {run.isPending && !r && <Skeleton h={200} />}
      {r && (
        <>
          <p style={{ margin: 0, color: "var(--muted)" }} data-testid="mc-meta">{t("mc.meta", { trials: fmt.num(r.trials), seed: r.seed })}{r.assumptions.signal ? ` · ${t("mc.signalShift", { d: fmt.flex(r.assumptions.signal.shift_days) })}` : ""}</p>
          {r.unavailable_reason && <Alert tone="warn">{t("mc.statuteNA")}: {r.unavailable_reason}</Alert>}
          <div style={{ overflowX: "auto" }}>
            <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }} data-testid="mc-table">
              <thead><tr><th style={th} /><th style={th}>P10</th><th style={th}>P50</th><th style={th}>P90</th></tr></thead>
              <tbody>
                <tr><th scope="row" style={{ textAlign: "start", padding: "0.5rem 0.7rem" }}>{t("mc.delayDays")}</th>{[r.delay_days.p10, r.delay_days.p50, r.delay_days.p90].map((v, i) => <td key={i} className="num" style={{ padding: "0.5rem 0.7rem" }} data-label={["P10", "P50", "P90"][i]}>{fmt.num(v)}</td>)}</tr>
                <Row label={t("gap.contract")} s={r.contractual} />
                <Row label={t("gap.statute")} s={r.statutory} badge={!!r.statutory} />
                <Row label={t("gap.shortfall")} s={r.shortfall} badge={!!r.shortfall} />
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <span className="chip" data-testid="mc-pgrace">{t("mc.pGrace")}: <strong className="num">{fmt.pct(r.prob_delay_exceeds_grace * 100, 1)}</strong></span>
            {r.prob_cap_binds != null && <span className="chip" data-testid="mc-pcap">{t("mc.pCap")}: <strong className="num">{fmt.pct(r.prob_cap_binds * 100, 1)}</strong></span>}
          </div>
          <Suspense fallback={<Skeleton h={220} />}>
            <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
              <figure style={{ margin: 0 }}><figcaption style={{ fontWeight: 600 }}>{t("mc.histogram")}</figcaption><div style={{ height: 220 }} role="img" aria-label={t("mc.histogram")}><McChart r={r} kind="hist" /></div></figure>
              <figure style={{ margin: 0 }}><figcaption style={{ fontWeight: 600 }}>{t("mc.curve")}</figcaption><div style={{ height: 220 }} role="img" aria-label={t("mc.curve")}><McChart r={r} kind="curve" /></div></figure>
            </div>
          </Suspense>
        </>
      )}
      <div style={{ display: "grid", gap: 8 }}>
        <button className="btn btn-ghost" style={{ justifySelf: "start" }} onClick={() => { setShowPortfolio(true); port.mutate(); }} data-testid="mc-portfolio">{t("mc.portfolio")}</button>
        {showPortfolio && port.isPending && <Skeleton h={120} />}
        {port.error && <Alert tone="danger">{(port.error as Error).message}</Alert>}
        {port.data && (
          <div style={{ overflowX: "auto" }} data-testid="mc-portfolio-table">
            <p style={{ color: "var(--muted)", margin: "0 0 6px" }}>{port.data.note}</p>
            <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
              <thead><tr><th style={th}>{t("mc.unit")}</th><th style={th}>{t("mc.currency")}</th><th style={th}>{t("gap.contract")} P50</th><th style={th}>{t("gap.contract")} P90</th><th style={th}>{t("gap.statute")} P90</th></tr></thead>
              <tbody>
                {port.data.rows.map((x) => (
                  <tr key={x.contract_id}>
                    <th scope="row" style={{ textAlign: "start", padding: "0.5rem 0.7rem" }} dir="auto">{x.name}</th>
                    <td style={{ padding: "0.5rem 0.7rem" }} data-label={t("mc.currency")}>{x.currency}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }} data-label="P50">{x.contractual ? fmt.flex(x.contractual.p50) : "–"}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }} data-label="P90">{x.contractual ? fmt.flex(x.contractual.p90) : "–"}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }} data-label="P90 statute">{x.statutory ? <>{fmt.flex(x.statutory.p90)} <UnreviewedBadge /></> : "–"}</td>
                  </tr>
                ))}
                {Object.entries(port.data.totals_by_currency).map(([cur, tot]) => (
                  <tr key={cur} style={{ fontWeight: 700, background: "var(--surface-2)" }} data-testid="mc-total">
                    <th scope="row" style={{ textAlign: "start", padding: "0.5rem 0.7rem" }}>{t("mc.total")} ({tot.contracts})</th>
                    <td style={{ padding: "0.5rem 0.7rem" }}>{cur}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }}>{tot.contractual ? fmt.flex(tot.contractual.p50) : "–"}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }}>{tot.contractual ? fmt.flex(tot.contractual.p90) : "–"}</td>
                    <td className="num" style={{ padding: "0.5rem 0.7rem" }}>{tot.statutory ? fmt.flex(tot.statutory.p90) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
