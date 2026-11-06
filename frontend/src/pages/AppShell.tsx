import { lazy, Suspense, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Route, Routes } from "react-router-dom";
import { ErrorState, Skeleton } from "../components/ui";
import { Sidebar } from "../components/Sidebar";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";
import { useContracts } from "../api/hooks";
import { useMedia } from "../state/useMedia";
import { useLocation } from "react-router-dom";
import { EmptyState } from "../components/ui";

const ContractLayout = lazy(() => import("./ContractLayout"));
const Accuracy = lazy(() => import("./Accuracy"));

function Pick() {
  const { t } = useTranslation();
  return <EmptyState title={t("shell.pickTitle")} body={t("shell.pickBody")} />;
}

export default function AppShell() {
  const { t } = useTranslation();
  const q = useContracts();
  const root = useRef<HTMLDivElement>(null);
  const narrow = useMedia("(max-width: 900px)");
  const hasContract = /\/contracts\//.test(useLocation().pathname);
  useMotion(root, ({ tier, dirSign }) => {
    if (tier === "reduced") return;
    gsap.from("[data-shell-side]", { x: -40 * dirSign, opacity: 0, duration: 0.7, ease: "dune" });
  });
  const sidebar = (
    <Sidebar
      contracts={q.data}
      loading={q.isLoading}
      error={q.error as Error | null}
      onRetry={() => void q.refetch()}
    />
  );
  return (
    <div
      ref={root}
      className="data-layer"
      style={{
        display: "grid",
        gap: "1.25rem",
        gridTemplateColumns: "minmax(250px, 330px) minmax(0, 1fr)",
        padding: "5.2rem 1rem 1.5rem",
        maxWidth: 1500,
        margin: "0 auto",
        alignItems: "start",
      }}
      data-app-shell
    >
      <style>{`@media (max-width: 900px){ [data-app-shell]{ grid-template-columns: minmax(0,1fr) !important; } }`}</style>
      <aside data-shell-side aria-label={t("shell.contracts")}>
        {/* Narrow screens: a fixed-height collapsible panel, so the list loading never pushes the content down (CLS). */}
        {narrow ? (
          <details open={!hasContract} className="card" style={{ padding: "0.6rem 0.9rem" }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>{t("shell.contracts")}</summary>
            <div style={{ paddingBlockStart: 10 }}>{sidebar}</div>
          </details>
        ) : (
          sidebar
        )}
      </aside>
      <section style={{ minWidth: 0 }}>
        <Suspense fallback={<Skeleton h={320} />}>
          <Routes>
            <Route index element={<Pick />} />
            <Route path="contracts/:id/*" element={<ContractLayout />} />
            <Route path="accuracy" element={<Accuracy />} />
            <Route
              path="*"
              element={<ErrorState title={t("errors.notFoundTitle")} message={t("errors.notFoundBody")} />}
            />
          </Routes>
        </Suspense>
      </section>
    </div>
  );
}
