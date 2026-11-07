import { useTranslation } from "react-i18next";
import type { CrossResult } from "../api/trust";

const SEV: Record<string, string> = { high: "var(--danger)", medium: "var(--warn)", low: "var(--info)" };

/**
 * Graph view (SVG): documents across the top, one row per attribute, a node per fact, grey edges document -> fact,
 * conflict edges in the alert colour between facts of the same attribute that disagree. Click a node to open the evidence.
 */
export function CrossGraph({ data, onPick, selected }: { data: CrossResult; onPick: (attribute: string) => void; selected: string | null }) {
  const { t } = useTranslation();
  const docs = data.graph.nodes.filter((n) => n.type === "document");
  const facts = data.graph.nodes.filter((n) => n.type === "fact");
  const attrs = [...new Set(facts.map((f) => f.attribute!))];
  const W = Math.max(640, 170 * docs.length + 130), colX = (i: number) => 130 + i * ((W - 150) / Math.max(docs.length, 1)) + 50;
  const rowY = (i: number) => 120 + i * 64;
  const docX = new Map(docs.map((d, i) => [d.id.replace("doc:", ""), colX(i)]));
  const pos = new Map(facts.map((f) => [f.id, { x: docX.get(f.doc_id!) ?? 0, y: rowY(attrs.indexOf(f.attribute!)) }]));
  const conflictAttr = new Set(data.conflicts.map((c) => c.attribute));
  const H = rowY(attrs.length) + 10;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("cross.graph")} style={{ width: "100%", height: "auto", minWidth: 520 }} data-testid="cross-graph">
      {docs.map((d, i) => (
        <g key={d.id} data-testid="graph-doc">
          <rect x={colX(i) - 62} y={10} width={124} height={34} rx={8} fill="var(--surface-2)" stroke={d.match === "uncertain" ? "var(--warn)" : "var(--line)"} strokeDasharray={d.match === "uncertain" ? "4 3" : undefined} />
          <text x={colX(i)} y={32} textAnchor="middle" fontSize={13} fill="var(--fg)" fontWeight={700}>{String(d.label)}</text>
        </g>
      ))}
      {data.graph.edges.filter((e) => e.kind === "states").map((e) => {
        const p = pos.get(e.target);
        const dx = docX.get(e.source.replace("doc:", ""));
        return p && dx ? <line key={e.target} x1={dx} y1={44} x2={p.x} y2={p.y - 16} stroke="var(--line)" /> : null;
      })}
      {attrs.map((a, i) => (
        <text key={a} x={6} y={rowY(i) + 4} fontSize={12} fill={conflictAttr.has(a) ? SEV[data.conflicts.find((c) => c.attribute === a)?.severity ?? "high"] : "var(--muted)"} fontWeight={conflictAttr.has(a) ? 700 : 400}>
          {facts.find((f) => f.attribute === a)?.attribute?.replace(/_/g, " ")}
        </text>
      ))}
      {data.graph.edges.filter((e) => e.kind === "conflict").map((e, i) => {
        const a = pos.get(e.source), b = pos.get(e.target);
        if (!a || !b) return null;
        const attr = (e.source.split(":")[1] ?? "").split("@")[0];
        const sev = data.conflicts.find((c) => c.attribute === attr)?.severity ?? "high";
        return <path key={i} data-testid="conflict-edge" d={`M${a.x} ${a.y} Q${(a.x + b.x) / 2} ${a.y - 34} ${b.x} ${b.y}`} fill="none" stroke={SEV[sev] ?? "var(--danger)"} strokeWidth={3} strokeDasharray="6 4" />;
      })}
      {facts.map((f) => {
        const p = pos.get(f.id)!;
        const bad = f.conflict;
        return (
          <g key={f.id} role="button" tabIndex={0} aria-label={`${f.attribute}: ${f.label}`} data-testid="graph-fact" data-conflict={bad ? "1" : "0"}
            style={{ cursor: "pointer" }} onClick={() => onPick(f.attribute!)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onPick(f.attribute!)}>
            <rect x={p.x - 66} y={p.y - 16} width={132} height={32} rx={16} fill="var(--surface)" stroke={bad ? "var(--danger)" : "var(--ok)"} strokeWidth={selected === f.attribute ? 4 : 2} />
            <text x={p.x} y={p.y + 5} textAnchor="middle" fontSize={12} fill="var(--fg)" className="num">{String(f.label).slice(0, 22)}</text>
          </g>
        );
      })}
    </svg>
  );
}
