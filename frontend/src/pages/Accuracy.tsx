import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";
import { useEvalStatus, useHealth } from "../api/hooks";
import { apiX, type EvalRunDetail } from "../api/trust";
import { Alert, EmptyState, ErrorState, Loader, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { AnimatedNumber } from "../motion/AnimatedNumber";

const RunChart = lazy(() => import("../components/RunChart"));
const ENGINES = ["claude_pdf", "azure_docint", "docling"];

export default function Accuracy() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const qc = useQueryClient();
  const health = useHealth();
  const [tab, setTab] = useState<"runs" | "engines">("runs");
  const [engine, setEngine] = useState("");
  const [runEngine, setRunEngine] = useState("claude_pdf");
  const [picked, setPicked] = useState<string | null>(null);
  const [watch, setWatch] = useState(false);
  const [needConfirm, setNeedConfirm] = useState<string | null>(null);
  const [startErr, setStartErr] = useState<string | null>(null);
  const runs = useQuery({ queryKey: ["runs", engine], queryFn: () => apiX.runs(engine || undefined) });
  const bake = useQuery({ queryKey: ["bakeoff"], queryFn: apiX.bakeoff, enabled: tab === "engines" });
  const status = useEvalStatus(watch);
  const runId = picked ?? runs.data?.runs[0]?.run_id ?? null;
  const detail = useQuery({ queryKey: ["run", runId], queryFn: () => apiX.run(runId!), enabled: !!runId });

  useEffect(() => {
    if (watch && status.data?.state === "done") {
      setWatch(false);
      setPicked(null);
      void qc.invalidateQueries({ queryKey: ["runs"] });
      void qc.invalidateQueries({ queryKey: ["bakeoff"] });
    }
  }, [status.data?.state, watch, qc]);

  const start = async (allow: boolean) => {
    setNeedConfirm(null);
    setStartErr(null);
    try {
      await apiX.evalRunEngine(runEngine, allow);
      setWatch(true);
    } catch (e) {
      if (e instanceof ApiError && e.code === "llm_confirmation_required") setNeedConfirm(e.message);
      else setStartErr((e as Error).message);
    }
  };
  const running = watch && status.data?.state !== "error" && status.data?.state !== "done";
  const d: EvalRunDetail | undefined = detail.data;
  const regs = Array.isArray(d?.regressions) ? (d!.regressions as unknown as { metric: string; before: number; after: number }[]) : [];
  const regressed = new Set(regs.map((r) => r.metric.replace(/\.f1$/, "")));
  const g = runs.data?.runs[0]?.golden;
  const th = { textAlign: "start" as const, padding: "0.5rem 0.7rem", fontSize: "0.85rem", color: "var(--muted)" };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)" };
  const n = (v: number | null | undefined, dp = 3) => (v == null ? "–" : fmt.num(v, dp));

  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.6rem" }}>{t("accuracy.title")}</h1>
        <Alert tone={g && g.real > 0 ? "info" : "warn"}>
          <span data-testid="golden-note">{g ? t("acc2.golden", { n: g.size, s: g.synthetic, r: g.real }) : t("acc2.noRuns")} {(!g || g.real === 0) && t("acc2.noReal")}</span>
        </Alert>
        <div role="tablist" aria-label={t("acc2.tabs")} className="tabs" style={{ justifySelf: "start" }}>
          {(["runs", "engines"] as const).map((k) => (
            <a key={k} role="tab" aria-selected={tab === k} data-testid={`acc-tab-${k}`} href={`#${k}`} onClick={(e) => { e.preventDefault(); setTab(k); }}
              style={{ background: tab === k ? "var(--accent-fill)" : undefined, color: tab === k ? "var(--on-accent)" : "var(--fg)" }}>{t(`acc2.${k}`)}</a>
          ))}
        </div>
      </section>

      {tab === "runs" && (
        <>
          <section className="card" style={{ padding: "1rem", display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
            <label style={{ display: "grid", gap: 4 }}>{t("acc2.filterEngine")}
              <select value={engine} onChange={(e) => setEngine(e.target.value)} style={{ minHeight: 44 }} data-testid="acc-engine-filter">
                <option value="">{t("obl.all")}</option>{ENGINES.map((x) => <option key={x} value={x}>{x}</option>)}
              </select></label>
            <label style={{ display: "grid", gap: 4 }}>{t("acc2.runEngine")}
              <select value={runEngine} onChange={(e) => setRunEngine(e.target.value)} style={{ minHeight: 44 }}>{ENGINES.map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
            {running ? (
              <div role="status" style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <Loader size={44} label={t("accuracy.running")} />{t("accuracy.running")}{" "}
                {status.data?.total ? <span className="num" data-testid="acc-progress">{fmt.num(status.data.done)}/{fmt.num(status.data.total)}</span> : null}
              </div>
            ) : (
              <button className="btn" onClick={() => void start(false)} disabled={!(health.data?.llm_configured ?? true) && runEngine !== "claude_pdf"} data-testid="acc-run">{t("acc2.run")}</button>
            )}
            {health.data && !health.data.llm_configured && <small style={{ color: "var(--muted)" }}>{t("acc2.cachedOnly")}</small>}
          </section>
          {needConfirm && (
            <Alert tone="warn"><div style={{ display: "grid", gap: 8 }}><span>{needConfirm}</span>
              <button className="btn" style={{ justifySelf: "start" }} onClick={() => void start(true)}>{t("accuracy.confirmRun")}</button></div></Alert>
          )}
          {(startErr || status.data?.state === "error") && <Alert tone="danger">{startErr ?? status.data?.message}</Alert>}
          {runs.isLoading && <Skeleton h={160} />}
          {runs.error && <ErrorState title={t("errors.generic")} message={(runs.error as Error).message} onRetry={() => void runs.refetch()} />}
          {runs.data && runs.data.runs.length === 0 && <EmptyState title={t("acc2.emptyTitle")} body={t("acc2.emptyBody")} />}
          {runs.data && runs.data.runs.length > 0 && (
            <section className="card" style={{ overflowX: "auto" }} aria-labelledby="hist-h">
              <h2 id="hist-h" className="display" style={{ margin: 0, padding: "0.8rem 1rem 0", fontSize: "1.2rem" }}>{t("acc2.history")}</h2>
              <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }} data-testid="run-table">
                <thead><tr><th style={th}>{t("acc2.when")}</th><th style={th}>{t("acc2.engine")}</th><th style={th}>{t("acc2.model")}</th><th style={th}>F1</th><th style={th}>{t("acc2.grounding")}</th><th style={th}>{t("acc2.halluc")}</th><th style={th}>{t("acc2.regress")}</th></tr></thead>
                <tbody>
                  {runs.data.runs.map((r) => (
                    <tr key={r.run_id} data-testid="run-row" onClick={() => setPicked(r.run_id)} style={{ cursor: "pointer", background: r.run_id === runId ? "var(--surface-2)" : undefined }}>
                      <th scope="row" style={{ ...td, textAlign: "start", fontWeight: 600 }}>
                        <button className="chip" onClick={() => setPicked(r.run_id)} aria-pressed={r.run_id === runId}>{r.timestamp.replace("T", " ").slice(0, 16)}</button>
                      </th>
                      <td style={td} data-label={t("acc2.engine")}>{r.engine}</td>
                      <td style={td} data-label={t("acc2.model")} dir="ltr">{r.model} {r.stub && <span className="chip" data-testid="stub-badge" style={{ color: "var(--warn)", borderColor: "var(--warn)" }}>{t("acc2.stub")}</span>}</td>
                      <td style={td} className="num" data-label="F1">{n(r.overall.f1)}</td>
                      <td style={td} className="num" data-label={t("acc2.grounding")}>{n(r.overall.grounding_pass_rate)}</td>
                      <td style={td} className="num" data-label={t("acc2.halluc")}>{fmt.num(r.overall.hallucinations)}</td>
                      <td style={td} data-label={t("acc2.regress")}>{r.regressions > 0 ? <span className="chip" style={{ color: "var(--danger)", borderColor: "var(--danger)" }}>{t("acc2.nRegress", { n: r.regressions })}</span> : r.compared_to ? t("acc2.none") : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {d && (
            <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }} aria-labelledby="det-h">
              <h2 id="det-h" className="display" style={{ margin: 0, fontSize: "1.2rem" }}>{t("acc2.perField")}</h2>
              <p style={{ margin: 0, color: "var(--muted)" }}>{d.model} · {d.engine} · {d.git_commit ?? "–"} · {t("acc2.golden", { n: d.golden.size, s: d.golden.synthetic, r: d.golden.real })}</p>
              {d.stub && <Alert tone="warn">{t("acc2.stubNote")}</Alert>}
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                {([["F1", d.overall.f1], [t("acc2.grounding"), d.overall.grounding_pass_rate], [t("acc2.abstain"), d.overall.abstention_rate]] as const).map(([l, v]) => (
                  <div key={l} className="card" style={{ padding: "0.6rem 1rem" }}><div style={{ color: "var(--muted)" }}>{l}</div>
                    <strong className="display num" style={{ fontSize: "1.6rem" }}>{v == null ? "–" : <AnimatedNumber value={v} format={(x) => fmt.num(x, 3)} />}</strong></div>
                ))}
                <div className="card" style={{ padding: "0.6rem 1rem" }}><div style={{ color: "var(--muted)" }}>{t("acc2.halluc")}</div><strong className="display num" style={{ fontSize: "1.6rem" }}>{fmt.num(d.overall.hallucinations)}</strong></div>
              </div>
              {regs.length > 0 && (
                <Alert tone="danger"><div data-testid="regressions"><strong>{t("acc2.regressions", { id: d.compared_to ?? "" })}</strong>
                  <ul style={{ margin: "4px 0 0", paddingInlineStart: "1.2rem" }}>{regs.map((r) => <li key={r.metric}>{r.metric}: {n(r.before)} → {n(r.after)}</li>)}</ul></div></Alert>
              )}
              <div style={{ height: 380 }} role="img" aria-label={t("acc2.perField")}>
                <Suspense fallback={<Skeleton h={380} />}>
                  <RunChart rows={Object.entries(d.fields).filter(([, v]) => v.f1 != null).map(([name, v]) => ({ name, f1: v.f1 as number, regressed: regressed.has(name) }))} />
                </Suspense>
              </div>
              <p style={{ margin: 0, color: "var(--muted)" }}>{t("acc2.tableMetric", { f1: n(d.table.row_f1), ok: d.table.sum_correct, docs: d.table.docs })}</p>
            </section>
          )}
        </>
      )}

      {tab === "engines" && (
        <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }} aria-labelledby="eng-h">
          <h2 id="eng-h" className="display" style={{ margin: 0, fontSize: "1.2rem" }}>{t("acc2.engines")}</h2>
          {bake.isLoading && <Skeleton h={160} />}
          {bake.data && (
            <>
              <Alert tone="info"><span data-testid="bake-note">{bake.data.note} {t("acc2.golden", { n: bake.data.golden_size, s: bake.data.golden_size - bake.data.golden_real, r: bake.data.golden_real })}</span></Alert>
              <div style={{ overflowX: "auto" }}>
                <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 760 }} data-testid="bake-table">
                  <thead><tr><th style={th}>{t("acc2.engine")}</th><th style={th}>{t("acc2.state")}</th><th style={th}>F1</th><th style={th}>{t("acc2.grounding")}</th><th style={th}>{t("acc2.halluc")}</th><th style={th}>{t("acc2.latency")}</th><th style={th}>{t("acc2.cost")}</th></tr></thead>
                  <tbody>
                    {bake.data.engines.map((e) => (
                      <tr key={e.name} data-testid="bake-row" data-engine={e.name}>
                        <th scope="row" style={{ ...td, textAlign: "start" }}>{e.name}<div style={{ fontWeight: 400, color: "var(--muted)", fontSize: "0.82rem" }}>{e.description}</div></th>
                        <td style={td} data-label={t("acc2.state")}>{e.configured ? (e.run ? t("acc2.ran") : t("acc2.ready")) : <span style={{ color: "var(--muted)" }}>{e.reason}</span>}</td>
                        <td style={td} className="num" data-label="F1">{n(e.run?.overall.f1)}</td>
                        <td style={td} className="num" data-label={t("acc2.grounding")}>{n(e.run?.overall.grounding_pass_rate)}</td>
                        <td style={td} className="num" data-label={t("acc2.halluc")}>{e.run ? fmt.num(e.run.overall.hallucinations) : "–"}</td>
                        <td style={td} className="num" data-label={t("acc2.latency")}>{e.run?.avg_latency_s != null ? `${fmt.num(e.run.avg_latency_s, 2)} s` : "–"}</td>
                        <td style={td} className="num" data-label={t("acc2.cost")}>{e.run?.cost_per_doc_usd != null ? fmt.num(e.run.cost_per_doc_usd, 4) : e.run ? t("acc2.costNA") : "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p style={{ margin: 0, color: "var(--muted)" }}>{t("acc2.costNote")}</p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
