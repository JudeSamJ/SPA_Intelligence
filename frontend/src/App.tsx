import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { AuthGate } from "./auth/AuthGate";
import { DisclaimerBar } from "./components/Disclaimer";
import { TopBar } from "./components/TopBar";
import { RouteFade, TransitionProvider } from "./motion/Transition";
import { loadDevtools } from "./motion/registry";

const Landing = lazy(() => import("./pages/Landing"));
const RoleSwitch = lazy(() => import("./pages/RoleSwitch"));
const Reset = lazy(() => import("./pages/Reset"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Login = lazy(() => import("./pages/Login"));

void loadDevtools(); // dev-only (?devtools=1); compiled away in production builds

export default function App() {
  return (
    <TransitionProvider>
      <TopBar />
      <main>
        <RouteFade>
          <Suspense fallback={<div style={{ minHeight: "100svh" }} aria-busy="true" />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/reset" element={<Reset />} />
              <Route
                path="/app/*"
                element={
                  <AuthGate>
                    <RoleSwitch />
                  </AuthGate>
                }
              />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </RouteFade>
      </main>
      <DisclaimerBar />
    </TransitionProvider>
  );
}
