import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { jsonResponse } from "../test/helpers";
import { authEnabled, setTokenProvider } from "./token";
import { useAuthedSrc } from "./useAuthedSrc";

afterEach(() => {
  setTokenProvider(null);
  vi.unstubAllGlobals();
});

describe("bearer token seam", () => {
  it("adds no Authorization header when sign-in is not configured", async () => {
    const f = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal("fetch", f);
    await api.contracts();
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
    expect(authEnabled()).toBe(false);
  });

  it("sends the token on API calls (and keeps JSON headers) once a provider is set", async () => {
    setTokenProvider(async () => "tok-123");
    const f = vi.fn(async () => jsonResponse({ rows: [] }));
    vi.stubGlobal("fetch", f);
    await api.penalty("abc", [30]);
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    const h = new Headers(init.headers);
    expect(h.get("Authorization")).toBe("Bearer tok-123");
    expect(h.get("Content-Type")).toBe("application/json");
  });

  it("images load directly when sign-in is off, and through an authenticated fetch when it is on", async () => {
    expect(renderHook(() => useAuthedSrc("/api/x.png")).result.current).toBe("/api/x.png");
    setTokenProvider(async () => "tok-9");
    const f = vi.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(["png"]) }) as unknown as Response);
    vi.stubGlobal("fetch", f);
    URL.createObjectURL = vi.fn(() => "blob:fake");
    URL.revokeObjectURL = vi.fn();
    const { result } = renderHook(() => useAuthedSrc("/api/y.png"));
    expect(result.current).toBeNull(); // nothing is requested without the header
    await vi.waitFor(() => expect(result.current).toBe("blob:fake"));
    expect(new Headers((f.mock.calls[0] as unknown as [string, RequestInit])[1].headers).get("Authorization")).toBe("Bearer tok-9");
  });
});
