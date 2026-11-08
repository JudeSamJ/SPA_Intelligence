import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type CSSProperties, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { json, request } from "../api/client";

type Mode = "signin" | "signup" | "forgot";

const field: CSSProperties = {
  minHeight: 46,
  width: "100%",
  boxSizing: "border-box",
  background: "rgba(255,255,255,.08)",
  border: "1px solid rgba(243,234,211,.4)",
  color: "#f3ead3",
  borderRadius: 10,
  padding: "0.5rem 0.8rem",
};
const linkBtn: CSSProperties = { background: "none", border: 0, color: "#f1cf8a", cursor: "pointer", textDecoration: "underline", minHeight: 44, padding: 0 };

/** Email + password sign-in, account creation and "forgot password", all through the server (the browser never holds a Supabase token). */
export function EmailSignIn({ confirmed }: { confirmed: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [note, setNote] = useState<string | null>(confirmed ? t("login.email.confirmed") : null);
  const path = { signin: "/auth/supabase/login", signup: "/auth/supabase/signup", forgot: "/auth/supabase/recover" }[mode];
  const go = useMutation({
    mutationFn: () => request<Record<string, unknown>>(path, json(mode === "forgot" ? { email } : { email, password })),
    onSuccess: () => {
      if (mode === "signin") void qc.invalidateQueries({ queryKey: ["auth-me"] }); // the page then redirects by itself
      else setNote(t(mode === "signup" ? "login.email.checkEmailSignup" : "login.email.checkEmailForgot"));
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setNote(null);
    go.mutate();
  };
  const switchTo = (m: Mode) => {
    setMode(m);
    setNote(null);
    go.reset();
  };
  return (
    <form onSubmit={submit} data-testid="email-form" style={{ display: "grid", gap: 10, textAlign: "start" }} noValidate>
      <h2 className="display" style={{ margin: 0, fontSize: "1.15rem", textAlign: "center", color: "#f3ead3" }}>{t(`login.email.title.${mode}`)}</h2>
      <label style={{ display: "grid", gap: 4 }}>
        <span>{t("login.email.email")}</span>
        <input type="email" autoComplete="email" dir="ltr" required value={email} onChange={(e) => setEmail(e.target.value)} style={field} />
      </label>
      {mode !== "forgot" && (
        <div style={{ display: "grid", gap: 4 }}>
          <label style={{ display: "grid", gap: 4 }}>
            <span>{t("login.email.password")}</span>
            <input
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              dir="ltr"
              required
              minLength={mode === "signup" ? 10 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={mode === "signup" ? "pw-help" : undefined}
              style={field}
            />
          </label>
          {mode === "signup" && <small id="pw-help" style={{ color: "#b9c4cc" }}>{t("login.email.passwordHelp")}</small>}
        </div>
      )}
      {note && <p role="status" data-testid="email-note" style={{ margin: 0, padding: "0.6rem 0.8rem", borderRadius: 12, background: "rgba(60,140,90,.25)", border: "1px solid rgba(150,220,170,.5)", color: "#dff5e6" }}>{note}</p>}
      {go.error && <p role="alert" data-testid="email-error" style={{ margin: 0, padding: "0.6rem 0.8rem", borderRadius: 12, background: "rgba(176,58,46,.25)", border: "1px solid rgba(255,160,140,.6)", color: "#ffd9d0" }}>{(go.error as Error).message}</p>}
      <button className="btn" type="submit" disabled={go.isPending || !email.trim() || (mode !== "forgot" && !password)} data-testid="email-submit" style={{ minHeight: 48 }}>
        {t(`login.email.submit.${mode}`)}
      </button>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0 16px", justifyContent: "center" }}>
        {mode !== "signin" && <button type="button" style={linkBtn} onClick={() => switchTo("signin")}>{t("login.email.toSignin")}</button>}
        {mode !== "signup" && <button type="button" style={linkBtn} onClick={() => switchTo("signup")}>{t("login.email.toSignup")}</button>}
        {mode === "signin" && <button type="button" style={linkBtn} onClick={() => switchTo("forgot")}>{t("login.email.toForgot")}</button>}
      </div>
    </form>
  );
}
