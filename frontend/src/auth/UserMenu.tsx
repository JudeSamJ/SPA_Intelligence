import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { useAuth } from "./useAuth";

const initials = (s: string) =>
  s
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("") || "?";

/** The signed-in person's GitHub picture at the right end of the navigation bar, with a small account menu. */
export function UserMenu() {
  const { t } = useTranslation();
  const me = useAuth();
  const [open, setOpen] = useState(false);
  const [broken, setBroken] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const u = me.data;

  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const down = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", down);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", down);
    };
  }, [open]);

  if (!u?.authenticated || u.mode === "off") return null;
  const name = u.name ?? u.login ?? "";
  const role = u.roles.includes("Spa.Reviewer") ? t("auth.roleReviewer") : t("auth.roleStaff");
  return (
    <div ref={box} style={{ position: "relative", flex: "none" }}>
      <button
        data-testid="user-menu-button"
        className="tap"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("auth.account", { name })}
        onClick={() => setOpen((o) => !o)}
        style={{
          width: 44,
          height: 44,
          padding: 0,
          borderRadius: "50%",
          border: "2px solid var(--gold)",
          background: "var(--surface-2)",
          color: "var(--fg)",
          cursor: "pointer",
          display: "grid",
          placeItems: "center",
          overflow: "hidden",
          fontWeight: 700,
        }}
      >
        {u.avatar_url && !broken ? (
          <img
            src={u.avatar_url}
            alt=""
            width={40}
            height={40}
            referrerPolicy="no-referrer"
            onError={() => setBroken(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <span aria-hidden="true">{initials(name)}</span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          data-testid="user-menu"
          className="glass"
          style={{
            position: "absolute",
            insetInlineEnd: 0,
            top: "calc(100% + 10px)",
            minWidth: 220,
            padding: "0.8rem",
            display: "grid",
            gap: 8,
            borderRadius: 16,
            background: "var(--surface)",
            zIndex: 90,
          }}
        >
          <div style={{ display: "grid", gap: 2 }}>
            <strong dir="auto">{name}</strong>
            {u.login && (
              <span dir="ltr" style={{ color: "var(--muted)", fontSize: "0.88rem" }}>
                @{u.login}
              </span>
            )}
            <span className="chip" style={{ justifySelf: "start", cursor: "default", marginBlockStart: 4 }}>
              {role}
            </span>
          </div>
          <button
            role="menuitem"
            className="btn btn-ghost"
            data-testid="sign-out"
            onClick={() =>
              void request("/auth/logout", { method: "POST" }).finally(() => window.location.assign("/login"))
            }
          >
            {t("auth.signOut")}
          </button>
        </div>
      )}
    </div>
  );
}
