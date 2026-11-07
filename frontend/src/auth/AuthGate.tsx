import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, request } from "../api/client";
import { Skeleton } from "../components/ui";

interface Me {
  authenticated: boolean;
  mode: string;
  name: string | null;
  roles: string[];
}

/**
 * Wraps the app area. Server auth off: renders the app unchanged. Signed in: renders the app plus a small "signed in as" chip.
 * Not signed in: a sign-in card (GitHub). The server enforces everything; this gate only decides what to show.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const me = useQuery({
    queryKey: ["auth-me"],
    queryFn: () => request<Me>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
  const unauthorized = me.error instanceof ApiError && me.error.status === 401;
  const cfg = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => request<{ mode: string; github: boolean }>("/auth/config"),
    enabled: unauthorized,
    retry: false,
  });

  if (me.isLoading) return <Skeleton h={320} />;
  if (me.data && (!me.data.authenticated || me.data.mode === "off")) return <>{children}</>;
  if (me.data?.authenticated) {
    return (
      <>
        <div
          data-testid="signed-in"
          style={{
            position: "fixed",
            bottom: "calc(var(--inset-bottom, 3rem) + 0.6rem)", // above the disclaimer banner, clear of the page content
            insetInlineEnd: "1rem",
            zIndex: 30,
            display: "flex",
            gap: 8,
            alignItems: "center",
            padding: "0.25rem 0.5rem 0.25rem 0.8rem",
            borderRadius: 999,
            background: "var(--surface)",
            border: "1px solid var(--line)",
            fontSize: "0.85rem",
          }}
        >
          <span dir="auto">{t("auth.signedInAs", { name: me.data.name ?? "" })}</span>
          <button
            className="chip"
            onClick={() =>
              void request("/auth/logout", { method: "POST" }).finally(() => window.location.assign("/"))
            }
          >
            {t("auth.signOut")}
          </button>
        </div>
        {children}
      </>
    );
  }
  if (unauthorized) {
    return (
      <section
        className="card"
        data-testid="sign-in"
        style={{ maxWidth: 520, margin: "6rem auto", padding: "1.6rem", display: "grid", gap: 12, textAlign: "center" }}
      >
        <h1 className="display" style={{ margin: 0, fontSize: "1.6rem" }}>
          {t("auth.signInTitle")}
        </h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("auth.signInBody")}</p>
        {cfg.data?.github ? (
          <a className="btn" href="/api/auth/github/login" data-testid="github-signin" style={{ justifySelf: "center" }}>
            {t("auth.signInGitHub")}
          </a>
        ) : (
          !cfg.isLoading && <p role="alert">{t("auth.notConfigured")}</p>
        )}
      </section>
    );
  }
  return <p role="alert">{t("errors.generic")}</p>;
}
