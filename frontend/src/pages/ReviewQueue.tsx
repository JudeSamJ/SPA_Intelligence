import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { apiX, type ReviewItem } from "../api/trust";
import { GroundingChip } from "../components/GroundingChip";
import { Alert, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";

function ItemCard({ it }: { it: ReviewItem }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const qc = useQueryClient();
  const [val, setVal] = useState("");
  const [note, setNote] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [mode, setMode] = useState<"idle" | "correct">("idle");
  const isRow = /^(payment_plan|ungrounded_rows|dated_clauses)\./.test(it.field);
  const done = () => void qc.invalidateQueries({ queryKey: ["review-queue"] });
  const mut = useMutation({
    mutationFn: (b: { action: "accept" | "correct" | "reject"; value?: unknown }) => apiX.review(it.contract_id, it.field, { ...b, note, reviewer }),
    onSuccess: () => { done(); void qc.invalidateQueries({ queryKey: ["contract", it.contract_id] }); },
  });
  const shown = it.value == null ? null : typeof it.value === "object" ? JSON.stringify(it.value) : String(it.value);
  const correct = () => {
    if (isRow) {
      const n = Number(val);
      mut.mutate({ action: "correct", value: { percent: n } });
    } else mut.mutate({ action: "correct", value: val });
  };
  return (
    <article className="card" data-testid="review-item" data-field={it.field} style={{ padding: "0.9rem 1rem", display: "grid", gap: 8 }}>
      <header style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <strong style={{ flex: 1, minWidth: 200 }} dir="auto">{it.contract_name} · {it.field}</strong>
        <GroundingChip item={{ grounding: { status: it.status }, confidence: it.confidence }} />
        <Link className="chip" to={`/app/contracts/${it.contract_id}/terms`}>{t("review.open")}</Link>
      </header>
      <div style={{ display: "grid", gap: 4 }}>
        <span>{t("review.extracted")}: <strong dir="auto">{shown ?? t("review.withheld")}</strong>{it.claimed_value && <> · {t("review.claimed")}: <strong dir="auto">{it.claimed_value}</strong></>}</span>
        {it.source_quote && <blockquote style={{ margin: 0, paddingInlineStart: 10, borderInlineStart: "3px solid var(--line)", color: "var(--muted)" }} dir="auto">{it.source_quote} {it.source_page ? <span className="num">({t("common.pageShort")} {fmt.num(it.source_page)})</span> : null}</blockquote>}
        {it.reasons.length > 0 && <small style={{ color: "var(--warn)" }}>{it.reasons.join("; ")}</small>}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <input placeholder={t("review.reviewer")} aria-label={t("review.reviewer")} value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ minHeight: 44, width: 150 }} />
        <input placeholder={t("review.note")} aria-label={t("review.note")} value={note} onChange={(e) => setNote(e.target.value)} style={{ minHeight: 44, flex: 1, minWidth: 160 }} />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <button className="btn" disabled={mut.isPending} onClick={() => mut.mutate({ action: "accept" })} data-testid="rv-accept">{t("review.accept")}</button>
        {mode === "idle" ? (
          <button className="btn btn-ghost" onClick={() => setMode("correct")} data-testid="rv-correct">{t("review.correct")}</button>
        ) : (
          <>
            <input aria-label={t("review.newValue")} value={val} onChange={(e) => setVal(e.target.value)} placeholder={isRow ? t("review.percent") : t("review.newValue")} style={{ minHeight: 44, width: 180 }} data-testid="rv-value" />
            <button className="btn" disabled={!val || mut.isPending} onClick={correct} data-testid="rv-save">{t("review.save")}</button>
          </>
        )}
        <button className="btn btn-ghost" disabled={mut.isPending} onClick={() => mut.mutate({ action: "reject" })} data-testid="rv-reject">{t("review.reject")}</button>
      </div>
      {mut.error && <Alert tone="danger">{(mut.error as Error).message}</Alert>}
    </article>
  );
}

export default function ReviewQueue() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["review-queue"], queryFn: apiX.reviewQueue });
  const contracts = [...new Map((q.data?.items ?? []).map((i) => [i.contract_id, i.contract_name])).entries()];
  const [exp, setExp] = useState<string | null>(null);
  const ex = useMutation({ mutationFn: (id: string) => apiX.goldenExport(id, true), onSuccess: (d) => setExp(d.path) });
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("review.title")}</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("review.intro")}</p>
        <p style={{ margin: 0 }}>{t("review.count", { n: q.data?.count ?? 0 })}</p>
      </section>
      {q.isLoading && <Skeleton h={200} />}
      {q.error && <ErrorState title={t("errors.generic")} message={(q.error as Error).message} onRetry={() => void q.refetch()} />}
      {q.data && q.data.count === 0 && <EmptyState title={t("review.emptyTitle")} body={t("review.emptyBody")} />}
      <div style={{ display: "grid", gap: 10 }}>{q.data?.items.map((it) => <ItemCard key={`${it.contract_id}:${it.field}`} it={it} />)}</div>
      {contracts.length > 0 && (
        <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }}>
          <strong>{t("review.golden")}</strong>
          <p style={{ margin: 0, color: "var(--muted)" }}>{t("review.goldenHelp")}</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {contracts.map(([id, name]) => <button key={id} className="btn btn-ghost" onClick={() => ex.mutate(id)}>{name}</button>)}
          </div>
          {exp && <Alert tone="ok">{t("review.exported", { path: exp })}</Alert>}
          {ex.error && <Alert tone="danger">{(ex.error as Error).message}</Alert>}
        </section>
      )}
    </div>
  );
}
