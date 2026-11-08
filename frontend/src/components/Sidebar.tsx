import { useEffect, useLayoutEffect, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, api, type ContractSummary } from "../api/client";
import { useHealth, useStatus, useUpload } from "../api/hooks";
import { useFmt } from "../i18n/format";
import { coinBurst } from "../motion/effects";
import { Flip } from "../motion/registry";
import { Tilt } from "../motion/Tilt";
import { usePrefs } from "../state/prefs";
import { useQueryClient } from "@tanstack/react-query";
import { Alert, ErrorState, Loader, Skeleton } from "./ui";

function StatusChip({ c }: { c: ContractSummary }) {
  const { t } = useTranslation();
  const tone =
    c.status === "extracted"
      ? "var(--ok)"
      : c.status === "error"
        ? "var(--danger)"
        : c.status === "running" || c.status === "queued" || c.status === "ocr"
          ? "var(--info)"
          : "var(--muted)";
  return (
    <span style={{ fontSize: "0.78rem", fontWeight: 700, color: tone }}>
      ● {t(`shell.status.${c.status}`)}
    </span>
  );
}

function Card({ c, active, onOpen }: { c: ContractSummary; active: boolean; onOpen: () => void }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  return (
    <Tilt>
      <button
        data-card
        data-flip-id={c.id}
        onClick={onOpen}
        aria-current={active ? "page" : undefined}
        className="card"
        style={{
          width: "100%",
          textAlign: "start",
          padding: "0.9rem 1rem",
          cursor: "pointer",
          color: "var(--fg)",
          borderColor: active ? "var(--accent)" : "var(--line)",
          boxShadow: active
            ? "0 0 0 1px var(--accent), 0 10px 30px -12px color-mix(in srgb, var(--gold) 50%, transparent)"
            : "none",
          display: "grid",
          gap: 4,
        }}
      >
        <span className="display" style={{ fontWeight: 700, fontSize: "1.05rem", overflowWrap: "anywhere" }}>
          {c.name}
        </span>
        <StatusChip c={c} />
        {active && (
          <span
            data-card-detail
            style={{
              display: "grid",
              gap: 2,
              color: "var(--muted)",
              fontSize: "0.9rem",
              marginBlockStart: 4,
            }}
          >
            {c.buyer && <span dir="auto">{c.buyer}</span>}
            {c.unit_id && (
              <span className="num" dir="ltr">
                {c.unit_id}
              </span>
            )}
            {c.price != null && <span className="num">{fmt.aed(c.price, 0)}</span>}
            <span>
              {t("shell.pages", { count: c.pages })}
              {c.warnings_count > 0 ? ` · ${t("shell.warnings", { count: c.warnings_count })}` : ""}
            </span>
          </span>
        )}
      </button>
    </Tilt>
  );
}

/** Drop zone with status polling. Mashrabiya loader while working; coin-burst when the contract is ready. */
function Upload({ onReady }: { onReady: (id: string) => void }) {
  const { t } = useTranslation();
  const { tier } = usePrefs();
  const up = useUpload();
  const ocrOn = !!useHealth().data?.ocr?.enabled;
  const qc = useQueryClient();
  const [id, setId] = useState<string | undefined>();
  const [over, setOver] = useState(false);
  const zone = useRef<HTMLLabelElement>(null);
  const st = useStatus(id, !!id);

  const phase = up.isPending
    ? "uploading"
    : id && st.data?.status !== "extracted" && st.data?.status !== "error"
      ? "reading"
      : "idle";
  const failed =
    up.error ?? (st.data?.status === "error" ? new ApiError(500, "extract", st.data.error ?? "") : null);

  useEffect(() => {
    if (st.data?.status === "extracted" && id) {
      if (zone.current) void coinBurst(zone.current, tier);
      void qc.invalidateQueries({ queryKey: ["contracts"] });
      onReady(id);
      setId(undefined);
    }
  }, [st.data?.status, id, onReady, qc, tier]);

  const pick = (f?: File | null) => {
    if (!f) return;
    up.mutate(f, { onSuccess: (r) => setId(r.id) });
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files[0]);
  };
  const busy = phase !== "idle";
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <label
        ref={zone}
        data-testid="dropzone"
        className="card"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        style={{
          display: "grid",
          placeItems: "center",
          textAlign: "center",
          gap: 6,
          padding: "1rem",
          cursor: "pointer",
          borderStyle: "dashed",
          borderColor: over ? "var(--accent)" : "var(--line)",
        }}
      >
        {busy ? (
          <Loader size={54} label={phase === "uploading" ? t("shell.uploading") : t("shell.reading")} />
        ) : null}
        <strong>
          {phase === "uploading"
            ? t("shell.uploading")
            : phase === "reading"
              ? t("shell.reading")
              : t("shell.dropTitle")}
        </strong>
        <small style={{ color: "var(--muted)" }}>{t(ocrOn ? "shell.dropHintOcr" : "shell.dropHint")}</small>
        <input
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      {failed && (
        <Alert tone="danger">
          {t("shell.uploadFailed")}: {failed.message}
        </Alert>
      )}
    </div>
  );
}

export function Sidebar({
  contracts,
  loading,
  error,
  onRetry,
}: {
  contracts?: ContractSummary[];
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const activeId = /\/contracts\/([0-9a-f]{64})/.exec(loc.pathname)?.[1];
  const flipState = useRef<Flip.FlipState | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();

  // Flip: the clicked card expands smoothly while the others reflow
  const open = (id: string) => {
    flipState.current = Flip.getState("[data-card]");
    void qc.prefetchQuery({ queryKey: ["contract", id], queryFn: () => api.contract(id) }).catch(() => {});
    nav(`/app/contracts/${id}/terms`);
  };
  useLayoutEffect(() => {
    if (flipState.current && tier !== "reduced") {
      Flip.from(flipState.current, {
        duration: 0.5,
        ease: "power3.inOut",
        targets: "[data-card]",
        absolute: false,
      });
    }
    flipState.current = null;
  }, [activeId, tier]);

  if (error) {
    const down = error instanceof ApiError && error.code === "network";
    return (
      <ErrorState
        title={down ? t("shell.serverDown") : t("errors.generic")}
        message={down ? t("shell.serverDownBody") : error.message}
        onRetry={onRetry}
      />
    );
  }
  const samples = (contracts ?? []).filter((c) => c.source === "sample");
  const uploads = (contracts ?? []).filter((c) => c.source === "upload");
  return (
    <div ref={list} style={{ display: "grid", gap: "1rem", position: "sticky", top: "5rem" }}>
      <h2 className="display" style={{ margin: 0, fontSize: "1.2rem" }}>
        {t("shell.samples")}
      </h2>
      {loading ? (
        <>
          <Skeleton h={64} />
          <Skeleton h={64} />
          <Skeleton h={64} />
        </>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {samples.map((c) => (
            <Card key={c.id} c={c} active={c.id === activeId} onOpen={() => open(c.id)} />
          ))}
        </div>
      )}
      <h2 className="display" style={{ margin: 0, fontSize: "1.2rem" }}>
        {t("shell.uploads")}
      </h2>
      <div style={{ display: "grid", gap: 10 }}>
        {uploads.length === 0 && !loading && (
          <small style={{ color: "var(--muted)" }}>{t("shell.noUploads")}</small>
        )}
        {uploads.map((c) => (
          <Card key={c.id} c={c} active={c.id === activeId} onOpen={() => open(c.id)} />
        ))}
      </div>
      <Upload onReady={(id) => nav(`/app/contracts/${id}/terms`)} />
    </div>
  );
}
