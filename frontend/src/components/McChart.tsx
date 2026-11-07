import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";
import type { MCResult } from "../api/trust";
import { useFmt } from "../i18n/format";

const tip = { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--fg)" };

/** Histogram of simulated delays, and the percentile curve (delay quantile vs exposure). Entrance only; no distortion. */
export default function McChart({ r, kind }: { r: MCResult; kind: "hist" | "curve" }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  if (kind === "hist") {
    const data = r.histogram.map((h) => ({ name: `${Math.round(h.from)}–${Math.round(h.to)}`, count: h.count }));
    return (
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fill: "var(--muted)", fontSize: 11 }} interval="preserveStartEnd" stroke="var(--line)" />
          <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} stroke="var(--line)" />
          <Tooltip contentStyle={tip} formatter={(v) => [fmt.num(Number(v)), t("mc.trialsLabel")]} labelFormatter={(l) => `${l} ${t("mc.days")}`} />
          <Bar dataKey="count" fill="var(--info)" radius={[4, 4, 0, 0]} isAnimationActive />
        </BarChart>
      </ResponsiveContainer>
    );
  }
  const data = r.quantiles.map((q) => ({ q: `P${q.q}`, contractual: q.contractual, statutory: q.statutory }));
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="q" tick={{ fill: "var(--muted)", fontSize: 11 }} interval={3} stroke="var(--line)" />
        <YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} tickFormatter={(v: number) => fmt.compact(v)} stroke="var(--line)" width={56} />
        <Tooltip contentStyle={tip} formatter={(v) => fmt.aed(Number(v), 0)} />
        <Legend />
        <Area type="monotone" dataKey="contractual" name={t("gap.contract")} stroke="var(--info)" fill="var(--info)" fillOpacity={0.25} isAnimationActive />
        {r.statutory && <Area type="monotone" dataKey="statutory" name={t("gap.statute")} stroke="var(--gold)" fill="var(--gold)" fillOpacity={0.2} isAnimationActive />}
        <Line dataKey="contractual" stroke="var(--info)" dot={false} legendType="none" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
