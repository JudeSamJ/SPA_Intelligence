import type { Me } from "./useAuth";

/** What kind of person is signed in. "off" means the server does not enforce sign-in (local development). */
export type Kind = "off" | "anon" | "pending" | "buyer" | "staff" | "reviewer" | "admin";

export function kindOf(me?: Me): Kind {
  if (!me) return "anon";
  if (me.mode === "off") return "off";
  if (!me.authenticated) return "anon";
  const r = me.roles;
  if (r.includes("Spa.Admin")) return "admin";
  if (r.includes("Spa.Reviewer")) return "reviewer";
  if (r.includes("Spa.Staff")) return "staff";
  if (r.includes("Spa.Buyer")) return "buyer";
  return "pending";
}

/** Which main-navigation links to show. The server enforces access; this only avoids showing links that would be refused. */
export function navFor(kind: Kind, loaded: boolean) {
  const everything = { app: true, watch: true, crosscheck: true, review: true, buyers: true, accuracy: true, users: false, mine: false };
  if (!loaded || kind === "off") return everything;
  if (kind === "buyer") return { app: false, watch: false, crosscheck: false, review: false, buyers: false, accuracy: false, users: false, mine: true };
  if (kind === "staff") return { ...everything, review: false, buyers: false };
  if (kind === "reviewer") return everything;
  if (kind === "admin") return { ...everything, users: true };
  return { app: false, watch: false, crosscheck: false, review: false, buyers: false, accuracy: false, users: false, mine: false };
}
