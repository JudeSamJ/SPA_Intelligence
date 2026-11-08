import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useContract, useContracts, useExtract, useHealth, useStatus } from "../api/hooks";
import { Tabs } from "../components/Tabs";
import { Alert, EmptyState, ErrorState, Loader, Skeleton } from "../components/ui";
import { coinBurst } from "../motion/effects";
import { gsap } from "../motion/registry";
import { scrollToTarget } from "../motion/scroll";
import { usePrefs } from "../state/prefs";
import { CurrencyContext } from "../i18n/format";
import { ContractCtx, type EvidenceTarget } from "./ctx";

const Terms = lazy(() => import("./Terms"));
const Penalty = lazy(() => import("./Penalty"));
const Cashflow = lazy(() => import("./Cashflow"));
const Assistant = lazy(() => import("./Assistant"));
const Gap = lazy(() => import("./Gap"));
const Obligations = lazy(() => import("./Obligations"));
const Playbook = lazy(() => import("./Playbook"));
const Erp = lazy(() => import("./Erp"));
const PdfPanel = lazy(() => import("../components/PdfPanel"));

function ExtractControls({ id, force }: { id: string; force: boolean }) {
  const { t } = useTranslation();
  const { tier } = usePrefs();
  const health = useHealth();
  const qc = useQueryClient();
  const ex = useExtract(id);
  const [started, setStarted] = useState(false);
  const st = useStatus(id, started);
  const btn = useRef<HTMLButtonElement>(null);
  const done = useRef(false);

  useEffect(() => {
    if (!started) return;
    if (st.data?.status === "extracted" && !done.current) {
      done.current = true;
      if (btn.current) void coinBurst(btn.current, tier);
      void qc.invalidateQueries({ queryKey: ["contract", id] });
      void qc.invalidateQueries({ queryKey: ["contracts"] });
      void qc.invalidateQueries({ queryKey: ["penalty", id] });
      void qc.invalidateQueries({ queryKey: ["cashflow", id] });
      setStarted(false);
    }
  }, [st.data?.status, started, id, qc, tier]);

  const running = ex.isPending || (started && st.data?.status !== "error" && st.data?.status !== "extracted");
  const err =
    ex.error ?? (st.data?.status === "error" ? new ApiError(500, "extract", st.data.error ?? "") : null);
  const configured = health.data?.llm_configured ?? true;
  return (
    <div style={{ display: "grid", gap: 10, justifyItems: "start" }}>
      <p style={{ color: "var(--muted)", margin: 0 }}>{t("shell.extractCost")}</p>
      {!configured && <Alert tone="warn">{t("shell.notConfigured")}</Alert>}
      {running ? (
        <div role="status" style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Loader size={56} label={t("shell.extracting")} />
          <strong>{t("shell.extracting")}</strong>
        </div>
      ) : (
        <button
          ref={btn}
          className="btn"
          disabled={!configured}
          onClick={() => {
            done.current = false;
            ex.mutate(force, { onSuccess: () => setStarted(true) });
          }}
        >
          {force ? t("shell.rerun") : t("shell.extract")}
        </button>
      )}
      {err && (
        <Alert tone="danger">
          {t("shell.extractFailed")}: {err.message}
        </Alert>
      )}
    </div>
  );
}

export default function ContractLayout() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const list = useContracts();
  const known = list.data?.find((c) => c.id === id);
  // Only request the detail when the list says it exists and is extracted: avoids a pointless (expected) 409.
  const q = useContract(id, known ? known.status === "extracted" : list.isFetched);
  const loc = useLocation();
  const [target, setTarget] = useState<EvidenceTarget | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();
  const seg = loc.pathname.split("/").pop();

  // tab content entrance
  useEffect(() => {
    if (!body.current) return;
    const tw = gsap.fromTo(
      body.current,
      { opacity: 0, y: tier === "reduced" ? 0 : 12 },
      { opacity: 1, y: 0, duration: tier === "reduced" ? 0.1 : 0.4, clearProps: "all" },
    );
    return () => void tw.kill();
  }, [seg, id, tier]);

  const openEvidence = useCallback((tg: EvidenceTarget) => {
    setTarget(tg);
    requestAnimationFrame(() => scrollToTarget("#pdf-panel", 90));
  }, []);
  const openPdf = useCallback((page: number) => openEvidence({ page }), [openEvidence]);
  const ctx = useMemo(
    () => (q.data ? { id, detail: q.data, openPdf, openEvidence } : null),
    [id, q.data, openPdf, openEvidence],
  );

  const ocrOn = !!useHealth().data?.ocr?.enabled;
  if (list.isLoading || q.isLoading) return <Skeleton h={360} />;
  const summary = known;
  if (summary && summary.status !== "extracted") {
    return (
      <EmptyState title={t("shell.notExtractedTitle")} body={summary?.name}>
        {summary?.scanned_suspect && !ocrOn ? (
          <Alert tone="warn">{t("shell.scanned")}</Alert>
        ) : (
          <>
            {summary?.scanned_suspect && <Alert tone="info">{t("shell.scannedOcr")}</Alert>}
            <ExtractControls id={id} force={false} />
          </>
        )}
      </EmptyState>
    );
  }
  if (q.error) {
    const missing = q.error instanceof ApiError && q.error.code === "not_found";
    return (
      <ErrorState
        title={missing ? t("errors.contractMissing") : t("errors.generic")}
        message={q.error.message}
        onRetry={() => void q.refetch()}
      />
    );
  }
  if (!ctx) return null;
  const c = ctx.detail.contract;
  const base = `/app/contracts/${id}`;
  return (
    <ContractCtx.Provider value={ctx}>
      <CurrencyContext.Provider value={c.currency ?? null}>
      <div style={{ display: "grid", gap: "1rem" }}>
        <header style={{ display: "grid", gap: 8 }}>
          <h1
            data-glitch-title
            className="display"
            style={{ margin: 0, fontSize: "clamp(1.6rem,3vw,2.3rem)", overflowWrap: "anywhere" }}
          >
            {ctx.detail.name}
          </h1>
          <p style={{ margin: 0, color: "var(--muted)" }} data-testid="extracted-info">
            {t("shell.extractedAt", { when: c.extracted_at ?? "", model: c.model ?? "" })}
          </p>
          <details style={{ color: "var(--muted)" }}>
            <summary style={{ cursor: "pointer", color: "var(--fg)" }}>🔄 {t("shell.rerun")}</summary>
            <div style={{ paddingBlockStart: 8 }}>
              <ExtractControls id={id} force />
            </div>
          </details>
          <Tabs base={base} />
        </header>
        <div
          data-split
          style={{
            display: "grid",
            gap: "1rem",
            gridTemplateColumns: target ? "minmax(0,1fr) minmax(320px, 42%)" : "minmax(0,1fr)",
            alignItems: "start",
          }}
        >
          <style>{`@media (max-width: 1100px){ [data-split]{ grid-template-columns: minmax(0,1fr) !important; } }`}</style>
          <div ref={body} data-split-main style={{ minWidth: 0 }}>
            <Suspense fallback={<Skeleton h={300} />}>
              <Routes>
                <Route index element={<Navigate to="terms" replace />} />
                <Route path="terms" element={<Terms />} />
                <Route path="gap" element={<Gap />} />
                <Route path="penalty" element={<Penalty />} />
                <Route path="cashflow" element={<Cashflow />} />
                <Route path="obligations" element={<Obligations />} />
                <Route path="playbook" element={<Playbook />} />
                <Route path="erp" element={<Erp />} />
                <Route path="assistant" element={<Assistant />} />
              </Routes>
            </Suspense>
          </div>
          {target && (
            <Suspense fallback={<Skeleton h={500} />}>
              <PdfPanel id={id} target={target} pages={known?.pages ?? 1} onClose={() => setTarget(null)} />
            </Suspense>
          )}
        </div>
      </div>
      </CurrencyContext.Provider>
    </ContractCtx.Provider>
  );
}
