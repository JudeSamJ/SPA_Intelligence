import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { Skeleton } from "../components/ui";
import { needsSignIn, useAuth } from "./useAuth";

/**
 * Wraps the app area. Server auth off, or signed in: renders the app. Not signed in: sends the visitor to the login page
 * (remembering where they were going). The server enforces everything; this gate only decides what to show.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const me = useAuth();
  const loc = useLocation();
  if (me.isLoading) return <Skeleton h={320} />;
  if (me.error) return <p role="alert">{t("errors.generic")}</p>;
  if (needsSignIn(me.data)) {
    return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  }
  return <>{children}</>;
}
