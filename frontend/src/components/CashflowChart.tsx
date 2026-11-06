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
import type { Period } from "../api/client";
import { useFmt } from "../i18n/format";
import { useMedia } from "../state/useMedia";

/** Stacked bars (time-based vs construction/handover-linked) + cumulative line. Lazy-loaded: it carries Recharts. */
export default function CashflowChart({ periods }: { periods: Period[] }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const narrow = useMedia("(max-width: 640px)");
  const tick = { fill: "var(--muted)", fontSize: 12 };
  const data = periods.map((p) => ({ ...p, label: fmt.period(p.period) }));
  return (
    <ResponsiveContainer>
      <ComposedChart
        data={data}
        margin={{ top: 10, right: narrow ? 4 : 12, bottom: 4, left: narrow ? 0 : 12 }}
      >
        <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={tick} interval="preserveStartEnd" minTickGap={14} stroke="var(--line)" />
        <YAxis
          yAxisId="l"
          tick={tick}
          tickFormatter={(v: number) => (narrow ? fmt.compact(v) : fmt.num(v))}
          stroke="var(--line)"
          width={narrow ? 46 : 84}
        />
        <YAxis
          yAxisId="r"
          hide={narrow}
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
        <Legend wrapperStyle={{ color: "var(--fg)", fontSize: narrow ? 12 : 14 }} />
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
  );
}
