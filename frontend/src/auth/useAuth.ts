import { useQuery } from "@tanstack/react-query";
import { request } from "../api/client";

export interface Me {
  authenticated: boolean;
  mode: string;
  name: string | null;
  login: string | null;
  avatar_url: string | null;
  roles: string[];
  pending?: boolean;
}

/** Who is signed in. The server always answers 200 (authenticated: false when nobody is), so no failed request is logged. */
export function useAuth() {
  return useQuery({ queryKey: ["auth-me"], queryFn: () => request<Me>("/auth/me"), retry: false, staleTime: 60_000 });
}

/** True when the server enforces sign-in and this visitor has not signed in yet. */
export const needsSignIn = (me?: Me) => !!me && me.mode !== "off" && !me.authenticated;

/** Only paths inside the app are accepted as a post-login destination. */
export const safeNext = (p: string | null): string =>
  p && /^\/app(\/[A-Za-z0-9._~%/-]{0,200})?$/.test(p) && !p.includes("//") && !p.includes("..") ? p : "/app";
