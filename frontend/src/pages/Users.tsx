import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { json, request } from "../api/client";
import { Alert, EmptyState, Skeleton } from "../components/ui";

interface UserRow {
  user_id: string;
  email: string;
  name: string;
  role: "staff" | "reviewer" | "buyer" | null;
  admin: boolean;
  via_assignment?: boolean;
  created_at: string;
  last_login_at: string | null;
}
const ROLES = ["staff", "reviewer", "buyer"] as const;

/** Administrator only: give each person who has signed up a role. A person with no role can sign in but sees nothing. */
export default function Users() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["users"], queryFn: () => request<{ users: UserRow[] }>("/users"), retry: false });
  const set = useMutation({
    mutationFn: (v: { id: string; role: string | null }) => request(`/users/${encodeURIComponent(v.id)}/role`, { ...json({ role: v.role }), method: "PUT" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["users"] }),
  });
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("users.title")}</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("users.intro")}</p>
        <ul style={{ margin: 0, paddingInlineStart: "1.1rem", color: "var(--muted)" }}>
          {ROLES.map((r) => <li key={r}>{t(`users.help.${r}`)}</li>)}
        </ul>
      </section>
      {list.isLoading && <Skeleton h={160} />}
      {list.error && <Alert tone="warn">{(list.error as Error).message}</Alert>}
      {set.error && <Alert tone="danger">{(set.error as Error).message}</Alert>}
      {list.data && list.data.users.length === 0 && <EmptyState title={t("users.empty")} body="" />}
      <div style={{ display: "grid", gap: 8 }}>
        {list.data?.users.map((u) => (
          <article key={u.user_id} className="card" data-testid="user-row" style={{ padding: "0.8rem 1rem", display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <div style={{ flex: "1 1 240px", display: "grid", gap: 2 }}>
              <strong dir="ltr" style={{ overflowWrap: "anywhere" }}>{u.email}</strong>
              {u.name && <span dir="auto" style={{ color: "var(--muted)" }}>{u.name}</span>}
            </div>
            {u.admin && <span className="chip">{t("users.admin")}</span>}
            {u.via_assignment && <span className="chip">{t("users.viaLink")}</span>}
            {!u.role && !u.admin && !u.via_assignment && <span className="chip" style={{ color: "var(--warn)" }}>{t("users.pending")}</span>}
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className="sr-only">{t("users.role")}</span>
              <select
                aria-label={t("users.roleFor", { email: u.email })}
                value={u.role ?? ""}
                disabled={set.isPending}
                onChange={(e) => set.mutate({ id: u.user_id, role: e.target.value || null })}
                style={{ minHeight: 44 }}
              >
                <option value="">{t("users.noRole")}</option>
                {ROLES.map((r) => <option key={r} value={r}>{t(`users.roles.${r}`)}</option>)}
              </select>
            </label>
          </article>
        ))}
      </div>
    </div>
  );
}
