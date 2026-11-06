import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError } from "../api/client";
import { useCashflow } from "../api/hooks";
import { MilestoneTimeline } from "../components/MilestoneTimeline";
import { Alert, EmptyState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { useContractCtx } from "./ctx";

export default function Cashflow() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, detail } = useContractCtx();
  const [gran, setGran] = useState<"quarter" | "month">("quarter");
  const [delay, setDelay] = useState<number | undefined>(undefined);
  const [pending, setPending] = useState<number | undefined>(undefined);
  useEffect(() => {
    const h = setTimeout(() => setDelay(pending), 250);
    return () => clearTimeout(h);
  }, [pending]);
  const q = useCashflow(id, gran, delay);

  if (q.error) return <EmptyState title={t("cashflow.unavailable")} body={(q.error as ApiError).message} />;
  const d = q.data;
  if (!d) return <Skeleton h={420} />;
  const shown = pending ?? d.at_risk.delay_days;
  const mismatch = Math.abs(d.at_risk.plan_total - d.price) > 0.01;
  const tick = { fill: "var(--muted)", fontSize: 12 };
  const th = {
    textAlign: "start" as const,
    padding: "0.5rem 0.7rem",
    color: "var(--muted)",
    fontSize: "0.85rem",
  };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)" };
  const data = d.periods.map((p) => ({ ...p, label: fmt.period(p.period) }));

  return (
    <div className="data-layer" style={{ display: "grid", gap: "1.2rem" }}>
      <section
        className="card"
        style={{ padding: "1rem", display: "flex", gap: "1.2rem", flexWrap: "wrap", alignItems: "center" }}
      >
        <div
          role="group"
          aria-label={t("cashflow.groupBy")}
          style={{ display: "flex", gap: 6, alignItems: "center" }}
        >
          <span style={{ color: "var(--muted)" }}>{t("cashflow.groupBy")}</span>
          {(["quarter", "month"] as const).map((g) => (
            <button
              key={g}
              className="chip"
              aria-pressed={gran === g}
              onClick={() => setGran(g)}
              style={{
                borderColor: gran === g ? "var(--accent)" : undefined,
                fontWeight: gran === g ? 700 : 400,
              }}
            >
              {t(`cashflow.${g}`)}
            </button>
          ))}
        </div>
        <label style={{ display: "grid", gap: 4, flex: 1, minWidth: 240 }}>
          <span style={{ color: "var(--muted)" }}>
            {t("cashflow.delay")}:{" "}
            <strong className="num" data-testid="cf-delay">
              {fmt.num(shown)} {t("penalty.daysUnit")}
            </strong>
          </span>
          <input
            type="range"
            min={0}
            max={d.max_delay_days}
            step={5}
            value={shown}
            onChange={(e) => setPending(Number(e.target.value))}
            aria-label={t("cashflow.delay")}
            style={{ accentColor: "var(--accent-fill)" }}
          />
        </label>
      </section>

      <section
        style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
        aria-live="polite"
      >
        {[
          ["linked", d.at_risk.linked_amount, (n: number) => fmt.aed(n, 0), "kpi-linked"],
          ["exposure", d.at_risk.penalty_exposure, (n: number) => fmt.aed(n, 0), "kpi-exposure"],
          ["atRisk", d.at_risk.at_risk_total, (n: number) => fmt.aed(n, 0), "kpi-atrisk"],
        ].map(([k, v, f, tid]) => (
          <div key={k as string} className="card" style={{ padding: "0.9rem 1rem" }}>
            <div style={{ color: "var(--muted)" }}>{t(`cashflow.${k}`)}</div>
            <div
              className="display"
              style={{ fontSize: "1.6rem", fontWeight: 700 }}
              data-testid={tid as string}
            >
              {v == null ? "–" : <AnimatedNumber value={v as number} format={f as (n: number) => string} />}
            </div>
          </div>
        ))}
        <div className="card" style={{ padding: "0.9rem 1rem" }}>
          <div style={{ color: "var(--muted)" }}>{t("cashflow.share")}</div>
          <div className="display num" style={{ fontSize: "1.6rem", fontWeight: 700 }}>
            {d.at_risk.linked_pct_of_plan != null ? fmt.pct(d.at_risk.linked_pct_of_plan, 1) : "–"}
          </div>
        </div>
      </section>
      {d.at_risk.penalty_note && <Alert tone="warn">{d.at_risk.penalty_note}</Alert>}
      {mismatch && (
        <Alert tone="danger">
          {t("cashflow.mismatch", { plan: fmt.aed(d.at_risk.plan_total, 0), price: fmt.aed(d.price, 0) })}
        </Alert>
      )}

      <section className="card" style={{ padding: "1rem" }} aria-label={t("cashflow.chart")}>
        <h2 className="display" style={{ margin: "0 0 0.6rem", fontSize: "1.25rem" }}>
          {t("cashflow.chart")}
        </h2>
        <div style={{ width: "100%", height: 360, direction: "ltr" }} data-testid="cashflow-chart">
          <ResponsiveContainer>
            <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 4, left: 12 }}>
              <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="label"
                tick={tick}
                interval="preserveStartEnd"
                minTickGap={14}
                stroke="var(--line)"
              />
              <YAxis
                yAxisId="l"
                tick={tick}
                tickFormatter={(v: number) => fmt.num(v)}
                stroke="var(--line)"
                width={84}
              />
              <YAxis
                yAxisId="r"
                orientation="right"
                tick={tick}
                tickFormatter={(v: number) => fmt.num(v)}
                stroke="var(--line)"
                width={84}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--surface)",
                  border: "1px solid var(--line)",
                  color: "var(--fg)",
                  borderRadius: 8,
                }}
                labelStyle={{ color: "var(--fg)" }}
                formatter={(v) => fmt.aed(Number(v), 2)}
              />
              <Legend wrapperStyle={{ color: "var(--fg)" }} />
              <Bar
                yAxisId="l"
                dataKey="safe_amount"
                name={t("cashflow.timeBased")}
                stackId="a"
                fill="var(--info)"
              />
              <Bar
                yAxisId="l"
                dataKey="at_risk_amount"
                name={t("cashflow.linkedSeries")}
                stackId="a"
                fill="var(--accent-fill)"
              />
              <Line
                yAxisId="r"
                dataKey="cumulative"
                name={t("cashflow.cumulative")}
                type="monotone"
                stroke="var(--fg)"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <details style={{ marginBlockStart: 10 }}>
          <summary style={{ cursor: "pointer" }}>
            {t("cashflow.chart")} ({t("cashflow.period")})
          </summary>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
              <thead>
                <tr>
                  <th scope="col" style={th}>
                    {t("cashflow.period")}
                  </th>
                  <th scope="col" style={th}>
                    {t("cashflow.due")}
                  </th>
                  <th scope="col" style={th}>
                    {t("cashflow.linkedSeries")}
                  </th>
                  <th scope="col" style={th}>
                    {t("cashflow.cumulative")}
                  </th>
                  <th scope="col" style={th}>
                    {t("cashflow.cumPct")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {d.periods.map((p) => (
                  <tr key={p.period} data-testid="period-row" style={{ opacity: p.is_past ? 0.75 : 1 }}>
                    <th scope="row" style={{ ...td, textAlign: "start" }} className="num">
                      {fmt.period(p.period)}
                    </th>
                    <td style={td} className="num">
                      {fmt.aed(p.amount_due, 2)}
                    </td>
                    <td style={td} className="num">
                      {fmt.aed(p.at_risk_amount, 2)}
                    </td>
                    <td style={td} className="num">
                      {fmt.aed(p.cumulative, 2)}
                    </td>
                    <td style={td} className="num">
                      {fmt.pct(p.cumulative_pct, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="card" style={{ padding: "1rem" }}>
        <h2 className="display" style={{ margin: "0 0 0.4rem", fontSize: "1.25rem" }}>
          {t("cashflow.timeline")}
        </h2>
        <MilestoneTimeline plan={detail.plan} asOf={d.as_of} />
        {d.unscheduled.length > 0 && (
          <Alert tone="warn">
            {t("cashflow.unscheduled")}:{" "}
            {d.unscheduled.map((u) => `${u.milestone} (${fmt.aed(u.amount, 0)})`).join(", ")}
          </Alert>
        )}
      </section>

      <section className="card" style={{ padding: "1rem" }}>
        <h2 className="display" style={{ margin: "0 0 0.4rem", fontSize: "1.1rem" }}>
          {t("cashflow.definition")}
        </h2>
        <p style={{ margin: 0, color: "var(--muted)", lineHeight: 1.6 }} data-testid="at-risk-definition">
          {d.at_risk_definition}
        </p>
      </section>
    </div>
  );
}
