import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFmt } from "../i18n/format";
import { useMedia } from "../state/useMedia";

export default function AccuracyChart({ rows }: { rows: Array<{ name: string; pct: number }> }) {
  const fmt = useFmt();
  const narrow = useMedia("(max-width: 640px)");
  return (
    <ResponsiveContainer>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ left: narrow ? 0 : 40, right: narrow ? 8 : 24, top: 4, bottom: 4 }}
      >
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
  );
}
