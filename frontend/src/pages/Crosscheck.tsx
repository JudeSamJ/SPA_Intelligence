import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiX, type CrossConflict, type CrossFact, type CrossResult } from "../api/trust";
import { CrossGraph } from "../components/CrossGraph";
import { PageViewer } from "../components/PageViewer";
import { Alert, EmptyState, ErrorState, Skeleton } from "../components/ui";

function Side({ setId, fact }: { setId: string; fact: CrossFact }) {
  const { t } = useTranslation();
  const hasPdf = fact.page != null && fact.quote;
  const ev = useQuery({ queryKey: ["xev", setId, fact.doc_id, fact.page, fact.quote], enabled: !!hasPdf && fact.doc_type !== "crm_export",
    queryFn: () => apiX.crossEvidence(setId, fact.doc_id, fact.page!, fact.quote!), retry: false });
  return (
    <div className="card" style={{ padding: "0.7rem", display: "grid", gap: 6 }} data-testid="side-doc">
      <strong>{t(`cross.docTypes.${fact.doc_type}`)} · <span dir="auto">{fact.shown}</span></strong>
      {fact.locator ? (
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("cross.crmCell", { file: fact.locator.file, row: fact.locator.row, col: fact.locator.column })}</p>
      ) : hasPdf ? (
        <PageViewer src={apiX.crossPageUrl(setId, fact.doc_id, fact.page!)} page={fact.page!} evidence={ev.data} height={300} label={`${fact.doc_type} ${t("common.page")} ${fact.page}`} />
      ) : <p style={{ margin: 0, color: "var(--muted)" }}>{t("evidence.noBox")}</p>}
      {fact.quote && <small style={{ color: "var(--muted)" }} dir="auto">{fact.quote}</small>}
    </div>
  );
}

export default function Crosscheck() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const sets = useQuery({ queryKey: ["xsets"], queryFn: apiX.crossSets });
  const [setId, setSetId] = useState<string>("");
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => { if (!setId && sets.data?.sets[0]) setSetId(sets.data.sets[0].set_id); }, [sets.data, setId]);
  const res = useQuery({ queryKey: ["xset", setId], queryFn: () => apiX.cross(setId, false), enabled: !!setId, retry: false });
  const read = useMutation({ mutationFn: () => apiX.cross(setId, true), onSuccess: (d) => qc.setQueryData(["xset", setId], d) });
  const d: CrossResult | undefined = read.data ?? res.data;
  const conflict: CrossConflict | undefined = d?.conflicts.find((c) => c.attribute === sel) ?? undefined;
  useEffect(() => setSel(null), [setId]);
  // two sides: first fact of the first two differing clusters (different shown value)
  const sides: CrossFact[] = conflict ? (() => { const seen = new Set<string>(); const out: CrossFact[] = []; for (const f of conflict.values) { if (!seen.has(f.shown)) { seen.add(f.shown); out.push(f); } } return out.slice(0, 2); })() : [];
  const sev = { high: "var(--danger)", medium: "var(--warn)", low: "var(--info)" };
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("cross.title")}</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("cross.intro")}</p>
        <label style={{ display: "grid", gap: 4, maxWidth: 420 }}>{t("cross.set")}
          <select value={setId} onChange={(e) => setSetId(e.target.value)} style={{ minHeight: 44 }} data-testid="cross-set">
            {sets.data?.sets.map((s) => <option key={s.set_id} value={s.set_id}>{s.unit_key} · {s.set_id}{s.synthetic ? ` (${t("cross.synthetic")})` : ""}</option>)}
          </select></label>
      </section>
      {(sets.isLoading || res.isLoading) && <Skeleton h={240} />}
      {sets.data?.sets.length === 0 && <EmptyState title={t("cross.none")} body={t("cross.noneBody")} />}
      {res.error && <ErrorState title={t("errors.generic")} message={(res.error as Error).message} onRetry={() => void res.refetch()} />}
      {d && (
        <>
          {d.synthetic && <Alert tone="info"><span data-testid="cross-synthetic">{t("cross.syntheticNote")}</span></Alert>}
          {d.pending.length > 0 && (
            <Alert tone="warn">
              <div style={{ display: "grid", gap: 8 }}>
                <span>{t("cross.pending", { docs: d.pending.map((p) => t(`cross.docTypes.${p}`)).join(", ") })}</span>
                <button className="btn btn-ghost" style={{ justifySelf: "start" }} disabled={read.isPending} onClick={() => read.mutate()} data-testid="cross-read">{read.isPending ? t("cross.reading") : t("cross.read")}</button>
                {read.error && <span style={{ color: "var(--danger)" }}>{(read.error as Error).message}</span>}
              </div>
            </Alert>
          )}
          <section className="card" style={{ padding: "0.8rem 1rem", display: "flex", gap: 8, flexWrap: "wrap" }} aria-label={t("cross.documents")}>
            {d.documents.map((x) => (
              <span key={x.id} className="chip" data-testid="cross-doc" data-match={x.match} title={x.note ?? undefined}
                style={{ borderColor: x.match === "uncertain" ? "var(--warn)" : x.match === "pending" || x.match === "unmatched" ? "var(--muted)" : "var(--ok)" }}>
                {t(`cross.docTypes.${x.type}`)} · {t(`cross.match.${x.match}`)}
              </span>
            ))}
          </section>
          {d.planted_score && (
            <Alert tone="ok"><span data-testid="cross-score">{t("cross.score", { p: d.planted_score.precision.toFixed(2), r: d.planted_score.recall.toFixed(2), tp: d.planted_score.tp, n: d.planted?.length ?? 0 })}</span></Alert>
          )}
          <section className="card" style={{ padding: "0.8rem", overflowX: "auto" }}>
            <CrossGraph data={d} selected={sel} onPick={(a) => setSel(d.conflicts.some((c) => c.attribute === a) ? a : null)} />
          </section>
          <section aria-label={t("cross.conflicts")} style={{ display: "grid", gap: 8 }}>
            <h2 className="display" style={{ margin: 0, fontSize: "1.2rem" }}>{t("cross.conflicts")} <span className="num" data-testid="cross-count">({d.conflicts.length})</span></h2>
            {d.conflicts.length === 0 && <Alert tone="ok">{t("cross.noConflicts")}</Alert>}
            {d.conflicts.map((c) => (
              <button key={c.attribute} className="card" data-testid="conflict" onClick={() => setSel(c.attribute)} aria-pressed={sel === c.attribute}
                style={{ textAlign: "start", padding: "0.7rem 0.9rem", cursor: "pointer", color: "var(--fg)", borderInlineStart: `4px solid ${sev[c.severity]}`, borderColor: sel === c.attribute ? "var(--accent)" : undefined }}>
                <strong style={{ color: sev[c.severity] }}>{t(`gap.severity.${c.severity}`)}</strong> · {c.label}
                {c.uncertain_match && <span className="chip" style={{ marginInlineStart: 8, color: "var(--warn)", borderColor: "var(--warn)" }}>{t("cross.uncertain")}</span>}
                <div style={{ color: "var(--muted)" }} dir="auto">{c.explanation}</div>
              </button>
            ))}
          </section>
          {conflict && (
            <section aria-label={t("cross.sideBySide")} data-testid="cross-side" style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
              {sides.map((f) => <Side key={`${f.doc_id}${f.shown}`} setId={d.set_id} fact={f} />)}
            </section>
          )}
        </>
      )}
    </div>
  );
}
