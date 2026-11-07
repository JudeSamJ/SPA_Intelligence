import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFmt } from "../i18n/format";
import { useMedia } from "../state/useMedia";

/** Per-field F1 for one run; regressed fields are drawn in the alert colour. */
export default function RunChart({ rows }: { rows: Array<{ name: string; f1: number; regressed: boolean }> }) {
  const fmt = useFmt();
  const narrow = useMedia("(max-width: 640px)");
  return (
    <ResponsiveContainer>
      <BarChart data={rows} layout="vertical" margin={{ left: narrow ? 0 : 40, right: narrow ? 8 : 24, top: 4, bottom: 4 }}>
        <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" domain={[0, 1]} tick={{ fill: "var(--muted)", fontSize: 12 }} tickFormatter={(v: number) => fmt.num(v, 1)} stroke="var(--line)" />
        <YAxis type="category" dataKey="name" width={150} tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
        <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--fg)" }} formatter={(v) => `F1 ${fmt.num(Number(v), 3)}`} />
        <Bar dataKey="f1" radius={[0, 6, 6, 0]}>
          {rows.map((r) => <Cell key={r.name} fill={r.regressed ? "var(--danger)" : "var(--info)"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
