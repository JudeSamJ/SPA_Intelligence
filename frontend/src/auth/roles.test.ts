import { describe, expect, it } from "vitest";
import { kindOf, navFor } from "./roles";
import type { Me } from "./useAuth";

const me = (over: Partial<Me>): Me => ({ authenticated: true, mode: "supabase", name: "x", login: "x@y.co", avatar_url: null, roles: [], ...over });

describe("roles", () => {
  it("maps server roles to one kind, highest first", () => {
    expect(kindOf(undefined)).toBe("anon");
    expect(kindOf(me({ mode: "off", authenticated: false }))).toBe("off");
    expect(kindOf(me({ authenticated: false }))).toBe("anon");
    expect(kindOf(me({ roles: [] }))).toBe("pending");
    expect(kindOf(me({ roles: ["Spa.Buyer"] }))).toBe("buyer");
    expect(kindOf(me({ roles: ["Spa.Staff"] }))).toBe("staff");
    expect(kindOf(me({ roles: ["Spa.Reviewer"] }))).toBe("reviewer");
    expect(kindOf(me({ roles: ["Spa.Reviewer", "Spa.Admin"] }))).toBe("admin");
  });

  it("shows each role only the links it may use", () => {
    expect(navFor("buyer", true)).toMatchObject({ mine: true, app: false, review: false, buyers: false, users: false, accuracy: false });
    expect(navFor("staff", true)).toMatchObject({ app: true, watch: true, review: false, buyers: false, users: false, mine: false });
    expect(navFor("reviewer", true)).toMatchObject({ review: true, buyers: true, users: false });
    expect(navFor("admin", true)).toMatchObject({ review: true, buyers: true, users: true });
    expect(Object.values(navFor("pending", true)).some(Boolean)).toBe(false);
  });

  it("keeps the full menu while the account is still loading or when the server does not enforce sign-in", () => {
    expect(navFor("anon", false)).toMatchObject({ app: true, review: true, users: false });
    expect(navFor("off", true)).toMatchObject({ app: true, review: true, buyers: true });
  });
});
