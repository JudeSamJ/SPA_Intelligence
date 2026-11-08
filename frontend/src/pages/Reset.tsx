import { useMutation } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { json, request } from "../api/client";
import { Alert } from "../components/ui";

/** Reads the one-time recovery token from the link's #fragment (it is never sent to a server by the browser), then removes it from the address bar. */
function takeToken(): string {
  const p = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const tok = p.get("access_token") ?? "";
  if (tok) window.history.replaceState(null, "", window.location.pathname);
  return tok;
}

export default function Reset() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  useEffect(() => void (document.title = t("reset.title")), [t]);
  const m = useMutation({ mutationFn: () => request<{ reset: boolean }>("/auth/supabase/reset", json({ token, password })) });
  const mismatch = again !== "" && again !== password;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!mismatch) m.mutate();
  };
  return (
    <div className="data-layer" style={{ display: "grid", placeItems: "center", minHeight: "70svh", padding: "6rem 1rem 3rem" }}>
      <section className="card" style={{ width: "min(94vw, 440px)", padding: "1.4rem", display: "grid", gap: 12 }} data-testid="reset-page">
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("reset.title")}</h1>
        {!token ? (
          <Alert tone="warn">{t("reset.noToken")}</Alert>
        ) : m.isSuccess ? (
          <>
            <Alert tone="ok">{t("reset.done")}</Alert>
            <Link className="btn" to="/login" style={{ justifySelf: "start" }}>{t("reset.toLogin")}</Link>
          </>
        ) : (
          <form onSubmit={submit} style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "grid", gap: 4 }}>
              <label style={{ display: "grid", gap: 4 }}>
                <span>{t("reset.password")}</span>
                <input type="password" autoComplete="new-password" dir="ltr" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} aria-describedby="pw-help" />
              </label>
              <small id="pw-help" style={{ color: "var(--muted)" }}>{t("login.email.passwordHelp")}</small>
            </div>
            <label style={{ display: "grid", gap: 4 }}>
              <span>{t("reset.again")}</span>
              <input type="password" autoComplete="new-password" dir="ltr" required value={again} onChange={(e) => setAgain(e.target.value)} />
            </label>
            {mismatch && <Alert tone="warn">{t("reset.mismatch")}</Alert>}
            {m.error && <Alert tone="danger">{(m.error as Error).message}</Alert>}
            <button className="btn" type="submit" disabled={m.isPending || !password || mismatch} data-testid="reset-submit">{t("reset.submit")}</button>
          </form>
        )}
      </section>
    </div>
  );
}
