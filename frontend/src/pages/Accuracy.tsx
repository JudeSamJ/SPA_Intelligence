import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError } from "../api/client";
import { useEvalResults, useEvalRun, useEvalStatus, useHealth } from "../api/hooks";
import { Alert, EmptyState, ErrorState, Loader, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { useQueryClient } from "@tanstack/react-query";

export default function Accuracy() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const qc = useQueryClient();
  const res = useEvalResults();
  const health = useHealth();
  const run = useEvalRun();
  const [watch, setWatch] = useState(false);
  const status = useEvalStatus(watch);
  const [needConfirm, setNeedConfirm] = useState<string | null>(null);

  useEffect(() => {
    if (watch && status.data?.state === "done") {
      setWatch(false);
      void qc.invalidateQueries({ queryKey: ["eval"] });
    }
  }, [status.data?.state, watch, qc]);

  const start = (allow: boolean) => {
    setNeedConfirm(null);
    run.mutate(allow, {
      onSuccess: () => setWatch(true),
      onError: (e) => {
        if (e instanceof ApiError && e.code === "llm_confirmation_required") setNeedConfirm(e.message);
      },
    });
  };
  const running = run.isPending || (watch && status.data?.state !== "error" && status.data?.state !== "done");
  const runError =
    run.error && !(run.error instanceof ApiError && run.error.code === "llm_confirmation_required")
      ? (run.error as Error).message
      : status.data?.state === "error"
        ? status.data.message
        : null;

  const controls = (
    <div style={{ display: "grid", gap: 10, justifyItems: "start" }}>
      {running ? (
        <div role="status" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Loader size={48} label={t("accuracy.running")} />
          {t("accuracy.running")}{" "}
          {status.data && status.data.total ? (
            <span className="num">
              {fmt.num(status.data.done)}/{fmt.num(status.data.total)}
            </span>
          ) : null}
        </div>
      ) : (
        <button className="btn btn-ghost" onClick={() => start(false)}>
          {t("accuracy.run")}
        </button>
      )}
      {needConfirm && (
        <Alert tone="warn">
          <div>{t("accuracy.needConfirm")}</div>
          <div style={{ color: "var(--muted)" }}>{needConfirm}</div>
          <button className="btn" style={{ marginBlockStart: 8 }} onClick={() => start(true)}>
            {t("accuracy.confirm")}
          </button>
        </Alert>
      )}
      {runError && <Alert tone="danger">{runError}</Alert>}
    </div>
  );

  if (res.isLoading) return <Skeleton h={320} />;
  if (res.error) {
    const e = res.error as ApiError;
    if (e.code === "no_results") return <EmptyState title={t("accuracy.none")}>{controls}</EmptyState>;
    return <ErrorState title={t("errors.generic")} message={e.message} onRetry={() => void res.refetch()} />;
  }
  const r = res.data!;
  const rows = Object.entries(r.fields).map(([name, v]) => ({ name, ...v, pct: v.accuracy * 100 }));
  const th = {
    textAlign: "start" as const,
    padding: "0.5rem 0.7rem",
    color: "var(--muted)",
    fontSize: "0.85rem",
  };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)" };
  const cur = health.data?.model;
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1.2rem" }}>
      <div>
        <h1 data-glitch-title className="display" style={{ margin: 0, fontSize: "clamp(1.6rem,3vw,2.3rem)" }}>
          {t("accuracy.title")}
        </h1>
        <p style={{ color: "var(--muted)", margin: "0.3rem 0 0" }}>
          {t("accuracy.generated", { when: r.generated_at, model: r.model })} ·{" "}
          {t("accuracy.files", { files: r.files.join(", ") })}
        </p>
      </div>
      {cur && cur !== r.model && (
        <Alert tone="warn">{t("accuracy.mismatchModel", { old: r.model, current: cur })}</Alert>
      )}
      <section
        style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}
      >
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ color: "var(--muted)" }}>{t("accuracy.values")}</div>
          <div className="display" style={{ fontSize: "2rem", fontWeight: 700 }} data-testid="acc-values">
            {r.overall.value_accuracy != null ? (
              <AnimatedNumber value={r.overall.value_accuracy * 100} format={(n) => fmt.pct(n, 1)} />
            ) : (
              "–"
            )}
          </div>
        </div>
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ color: "var(--muted)" }}>{t("accuracy.quotes")}</div>
          <div className="display" style={{ fontSize: "2rem", fontWeight: 700 }} data-testid="acc-quotes">
            {r.overall.quote_accuracy != null ? (
              <AnimatedNumber value={r.overall.quote_accuracy * 100} format={(n) => fmt.pct(n, 1)} />
            ) : (
              "–"
            )}
          </div>
        </div>
        <div className="card" style={{ padding: "1rem" }}>
          <div style={{ color: "var(--muted)" }}>{t("accuracy.tests")}</div>
          <div className="display num" style={{ fontSize: "2rem", fontWeight: 700 }} data-testid="acc-tests">
            {fmt.num(r.penalty_tests.passed)}/{fmt.num(r.penalty_tests.total)}
          </div>
        </div>
      </section>
      <section className="card" style={{ padding: "1rem" }} aria-label={t("accuracy.chart")}>
        <h2 className="display" style={{ margin: "0 0 0.5rem", fontSize: "1.25rem" }}>
          {t("accuracy.chart")}
        </h2>
        <div style={{ width: "100%", height: Math.max(260, rows.length * 26), direction: "ltr" }}>
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ left: 40, right: 24, top: 4, bottom: 4 }}>
              <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 100]}
                tick={{ fill: "var(--muted)", fontSize: 12 }}
                tickFormatter={(v: number) => `${fmt.num(v)}%`}
                stroke="var(--line)"
              />
              <YAxis
                type="category"
                dataKey="name"
                width={190}
                tick={{ fill: "var(--muted)", fontSize: 12 }}
                stroke="var(--line)"
              />
              <Tooltip
                contentStyle={{
                  background: "var(--surface)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  color: "var(--fg)",
                }}
                formatter={(v) => `${fmt.num(Number(v), 1)}%`}
              />
              <Bar dataKey="pct" fill="var(--info)" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="card" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
          <thead>
            <tr>
              <th scope="col" style={th}>
                {t("accuracy.field")}
              </th>
              <th scope="col" style={th}>
                {t("accuracy.correct")}
              </th>
              <th scope="col" style={th}>
                {t("accuracy.accuracy")}
              </th>
              <th scope="col" style={th}>
                {t("accuracy.quoteCol")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.name} data-testid="acc-row">
                <th scope="row" style={{ ...td, textAlign: "start" }}>
                  {v.name}
                </th>
                <td style={td} className="num">
                  {fmt.num(v.correct)}/{fmt.num(v.total)}
                </td>
                <td style={td} className="num">
                  {fmt.pct(v.pct, 0)}
                </td>
                <td style={td} className="num">
                  {v.quote_total ? `${fmt.num(v.quote_valid)}/${fmt.num(v.quote_total)}` : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {controls}
    </div>
  );
}
