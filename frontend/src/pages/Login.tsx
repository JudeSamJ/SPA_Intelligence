import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useSearchParams } from "react-router-dom";
import { request } from "../api/client";
import { needsSignIn, safeNext, useAuth } from "../auth/useAuth";
import { Skeleton } from "../components/ui";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";
import { Dunes } from "../scenes/Dunes";
import { MashrabiyaBand } from "../scenes/Mashrabiya";
import { Skyline } from "../scenes/Skyline";
import { Stars } from "../scenes/Stars";
import { useRef } from "react";

const ERRORS = ["state", "failed", "cancelled", "not_allowed"];

function GitHubMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.88.87 2.34.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

/** Dedicated sign-in page in the site's UAE look: dusk sky, stars, the skyline, dunes and a mashrabiya band. */
export default function Login() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const err = params.get("error");
  const me = useAuth();
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => request<{ mode: string; github: boolean }>("/auth/config"), retry: false });
  const card = useRef<HTMLElement>(null);

  useEffect(() => {
    document.documentElement.dataset.scene = "dark"; // dark cinematic page in both themes, like the landing page
    return () => void delete document.documentElement.dataset.scene;
  }, []);
  useMotion(card, ({ tier }) => {
    if (tier === "reduced" || !card.current) return;
    gsap.from(card.current, { y: 24, opacity: 0, duration: 0.7, ease: "power3.out", clearProps: "transform,opacity" });
  }, []);

  if (me.data && !needsSignIn(me.data)) return <Navigate to={next} replace />; // already signed in, or server auth is off
  const known = err && ERRORS.includes(err);

  return (
    <div
      data-testid="login-page"
      style={{
        position: "relative",
        minHeight: "100svh",
        overflow: "hidden",
        display: "grid",
        placeItems: "center",
        padding: "calc(var(--inset-top, 5rem) + 1rem) 1rem calc(var(--inset-bottom, 3rem) + 2rem)",
        background: "linear-gradient(180deg,#2d2a5a 0%,#6b3a68 52%,#f0a35a 100%)", // same dusk sky as the landing hero
        color: "#f3ead3",
      }}
    >
      <Stars count={60} />
      <div aria-hidden="true" style={{ position: "absolute", insetInline: 0, bottom: "10%", height: "58%", color: "#150f24" }}>
        <Skyline initialTheme="dusk" />
      </div>
      <div aria-hidden="true" style={{ position: "absolute", insetInline: "-10%", bottom: 0, height: "34%" }}>
        <Dunes layers={3} />
      </div>
      <section
        ref={card}
        aria-labelledby="login-h"
        className="glass"
        style={{
          position: "relative",
          zIndex: 2,
          width: "min(92vw, 430px)",
          padding: "0 0 1.8rem",
          borderRadius: 24,
          overflow: "hidden",
          background: "rgba(11,27,43,.78)",
          border: "1px solid rgba(243,234,211,.28)",
          display: "grid",
          gap: "0.9rem",
          textAlign: "center",
          boxShadow: "0 30px 80px -30px rgba(0,0,0,.7)",
        }}
      >
        <MashrabiyaBand height={26} opacity={0.55} />
        <div style={{ display: "grid", gap: "0.9rem", padding: "0.4rem 1.6rem 0" }}>
          <h1 id="login-h" className="display" style={{ margin: 0, fontSize: "clamp(1.6rem,5vw,2rem)", color: "#f3ead3" }}>
            {t("login.title")}
          </h1>
          <p style={{ margin: 0, color: "#d6dde3", lineHeight: 1.55 }}>{t("login.subtitle")}</p>

          {known && (
            <p role="alert" data-testid="login-error" style={{ margin: 0, padding: "0.6rem 0.8rem", borderRadius: 12, background: "rgba(176,58,46,.25)", border: "1px solid rgba(255,160,140,.6)", color: "#ffd9d0" }}>
              {t(`login.errors.${err}`, { login: params.get("login") ?? "" })}
            </p>
          )}

          {me.isLoading || cfg.isLoading ? (
            <Skeleton h={48} />
          ) : cfg.data?.github ? (
            <a
              className="btn"
              data-testid="github-signin"
              href={`/api/auth/github/login?next=${encodeURIComponent(next)}`}
              style={{ justifySelf: "center", display: "inline-flex", gap: 10, alignItems: "center", minHeight: 48 }}
            >
              <GitHubMark /> {t("login.github")}
            </a>
          ) : (
            <p role="alert" style={{ margin: 0, color: "#ffd9d0" }}>{t("login.notConfigured")}</p>
          )}

          <p style={{ margin: 0, fontSize: "0.85rem", color: "#b9c4cc" }}>{t("login.approvedOnly")}</p>
          <p style={{ margin: 0, fontSize: "0.8rem", color: "#9fb0bb" }}>{t("login.privacy")}</p>
          <a href="/" style={{ color: "#f1cf8a", justifySelf: "center", minHeight: 44, display: "inline-flex", alignItems: "center" }}>
            {t("login.back")}
          </a>
        </div>
      </section>
    </div>
  );
}
