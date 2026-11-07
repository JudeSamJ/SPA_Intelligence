import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiX, type PlaybookRow } from "../api/trust";
import { EvidenceLink } from "../components/EvidenceLink";
import { Alert, ErrorState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { useContractCtx } from "./ctx";

const TONE: Record<string, string> = { pass: "var(--ok)", fail: "var(--danger)", needs_review: "var(--warn)", not_run: "var(--muted)" };

function Redline({ ops }: { ops: { op: string; old: string; new: string }[] }) {
  const { t } = useTranslation();
  return (
    <p data-testid="redline" aria-label={t("playbook.redline")} style={{ margin: 0, lineHeight: 1.7 }} dir="auto">
      {ops.map((o, i) => {
        if (o.op === "equal") return <span key={i}>{o.old} </span>;
        return (
          <span key={i}>
            {o.old && <del style={{ background: "var(--danger-bg)", color: "var(--danger)" }}>{o.old}</del>}{" "}
            {o.new && <ins style={{ background: "var(--ok-bg)", color: "var(--ok)", textDecoration: "none" }}>{o.new}</ins>}{" "}
          </span>
        );
      })}
    </p>
  );
}

function Card({ r }: { r: PlaybookRow }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const s = r.suggestion;
  return (
    <article className="card" data-testid="pb-card" data-status={r.status} style={{ padding: "0.9rem 1rem", display: "grid", gap: 8, borderInlineStart: `4px solid ${TONE[r.status]}` }}>
      <header style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <strong style={{ flex: 1, minWidth: 220 }}>{r.title}</strong>
        <span className="chip" style={{ color: TONE[r.status], borderColor: TONE[r.status] }}>{t(`playbook.status.${r.status}`)}</span>
        <span className="chip">{t(`gap.severity.${r.severity === "high" || r.severity === "medium" ? r.severity : "low"}`)}</span>
        <span className="chip">{r.kind === "deterministic" ? t("playbook.code") : t("playbook.llm")}</span>
        {r.confidence != null && r.kind === "qualitative" && <span className="chip num">{fmt.pct(r.confidence * 100, 0)}</span>}
        {r.evidence?.page && <EvidenceLink page={r.evidence.page} quote={r.evidence.quote} />}
      </header>
      <p style={{ margin: 0, color: "var(--muted)" }}>{r.reason}</p>
      {s && !s.available && <Alert tone="warn">{s.flag ?? t("playbook.noApproved")}</Alert>}
      {s?.available && (
        <details open={r.status === "fail"}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>{t("playbook.suggested")} · {s.file} · v{s.version}</summary>
          <p style={{ color: "var(--muted)", margin: "6px 0" }}>{t("playbook.approvedBy")}: {s.approved_by} · <em>{s.status}</em></p>
          {s.redline ? <Redline ops={s.redline} /> : <p dir="auto" style={{ margin: 0 }}>{s.text}</p>}
        </details>
      )}
    </article>
  );
}

export default function Playbook() {
  const { t } = useTranslation();
  const { id } = useContractCtx();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["playbook", id], queryFn: () => apiX.playbook(id, false), retry: false });
  const run = useMutation({ mutationFn: () => apiX.playbook(id, true), onSuccess: (d) => qc.setQueryData(["playbook", id], d) });
  const d = q.data;
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }}>
        <h2 className="display" style={{ margin: 0, fontSize: "1.3rem" }}>{t("playbook.title")}</h2>
        <Alert tone="warn"><span data-testid="pb-example">{t("playbook.example")}</span></Alert>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("playbook.internal")}</p>
        {d && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }} data-testid="pb-summary">
            {(["pass", "fail", "needs_review", "not_run"] as const).map((k) => (
              <span key={k} className="chip" style={{ color: TONE[k], borderColor: TONE[k] }}>{t(`playbook.status.${k}`)}: <strong className="num">{d.summary[k] ?? 0}</strong></span>
            ))}
            <span style={{ flex: 1 }} />
            {!d.llm_run && <button className="btn btn-ghost" disabled={run.isPending} onClick={() => run.mutate()} data-testid="pb-run">{run.isPending ? t("playbook.running") : t("playbook.runLlm")}</button>}
            <a className="btn btn-ghost" href={apiX.playbookCsvUrl(id)} download>{t("playbook.export")}</a>
          </div>
        )}
        {!d?.llm_run && d && <p style={{ margin: 0, color: "var(--muted)" }}>{t("playbook.llmCost")}</p>}
        {run.error && <Alert tone="danger">{(run.error as Error).message}</Alert>}
      </section>
      {q.isLoading && <Skeleton h={260} />}
      {q.error && <ErrorState title={t("errors.generic")} message={(q.error as Error).message} onRetry={() => void q.refetch()} />}
      {d && <div style={{ display: "grid", gap: 10 }}>{d.results.map((r) => <Card key={r.rule_id} r={r} />)}</div>}
    </div>
  );
}
