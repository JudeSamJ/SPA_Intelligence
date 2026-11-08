import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { useAuth } from "../auth/useAuth";

/** Signed in, but no administrator has given this account a role yet. */
export default function Pending() {
  const { t } = useTranslation();
  const me = useAuth();
  return (
    <div className="data-layer" style={{ display: "grid", placeItems: "center", minHeight: "70svh", padding: "6rem 1rem 3rem" }}>
      <section className="card" data-testid="pending-page" style={{ width: "min(94vw, 520px)", padding: "1.6rem", display: "grid", gap: 12 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.6rem" }}>{t("pending.title")}</h1>
        <p style={{ margin: 0 }}>{t("pending.body", { email: me.data?.login ?? "" })}</p>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("pending.hint")}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn" onClick={() => void me.refetch()}>{t("pending.check")}</button>
          <button className="btn btn-ghost" onClick={() => void request("/auth/logout", { method: "POST" }).finally(() => window.location.assign("/login"))}>{t("auth.signOut")}</button>
        </div>
      </section>
    </div>
  );
}
