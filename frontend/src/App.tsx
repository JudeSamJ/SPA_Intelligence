import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { DisclaimerBar } from "./components/Disclaimer";
import { TopBar } from "./components/TopBar";
import { Cursor } from "./motion/Cursor";
import { RouteFade, TransitionProvider } from "./motion/Transition";
import { loadDevtools } from "./motion/registry";

const Landing = lazy(() => import("./pages/Landing"));
const AppShell = lazy(() => import("./pages/AppShell"));
const NotFound = lazy(() => import("./pages/NotFound"));

void loadDevtools(); // dev-only (?devtools=1); compiled away in production builds

export default function App() {
  return (
    <TransitionProvider>
      <Cursor />
      <TopBar />
      <main>
        <RouteFade>
          <Suspense fallback={<div style={{ minHeight: "100svh" }} aria-busy="true" />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/app/*" element={<AppShell />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </RouteFade>
      </main>
      <DisclaimerBar />
    </TransitionProvider>
  );
}
