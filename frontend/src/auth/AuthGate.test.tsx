import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse } from "../test/helpers";
import { AuthGate } from "./AuthGate";

afterEach(() => vi.unstubAllGlobals());

const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PrefsProvider>
        <AuthGate>
          <p>the app</p>
        </AuthGate>
      </PrefsProvider>
    </QueryClientProvider>,
  );

const route = (map: Record<string, Response>) =>
  vi.fn(async (u: string) => {
    const hit = Object.entries(map).find(([k]) => u.endsWith(k));
    return hit ? hit[1].clone() : jsonResponse({ error: { code: "x", message: "x" } }, 404);
  });

describe("AuthGate", () => {
  it("shows the app unchanged when server authentication is off", async () => {
    vi.stubGlobal("fetch", route({ "/auth/me": jsonResponse({ authenticated: false, mode: "off", name: null, roles: [] }) }));
    mount();
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
    expect(screen.queryByTestId("signed-in")).toBeNull();
  });

  it("shows a GitHub sign-in card, not the app, when the server answers 401", async () => {
    vi.stubGlobal(
      "fetch",
      route({
        "/auth/me": jsonResponse({ error: { code: "unauthorized", message: "Sign in" } }, 401),
        "/auth/config": jsonResponse({ mode: "apikey", github: true }),
      }),
    );
    mount();
    const btn = await screen.findByTestId("github-signin");
    expect(btn).toHaveAttribute("href", "/api/auth/github/login");
    expect(screen.queryByText("the app")).toBeNull();
  });

  it("says sign-in is not configured when GitHub is not set up", async () => {
    vi.stubGlobal(
      "fetch",
      route({
        "/auth/me": jsonResponse({ error: { code: "unauthorized", message: "Sign in" } }, 401),
        "/auth/config": jsonResponse({ mode: "apikey", github: false }),
      }),
    );
    mount();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not configured/i));
    expect(screen.queryByTestId("github-signin")).toBeNull();
  });

  it("shows the app with who is signed in once authenticated", async () => {
    vi.stubGlobal("fetch", route({ "/auth/me": jsonResponse({ authenticated: true, mode: "apikey", name: "Alice A", roles: ["Spa.Reviewer"] }) }));
    mount();
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
    expect(screen.getByTestId("signed-in")).toHaveTextContent("Signed in as Alice A");
  });

  it("sends X-Requested-With on every API call (CSRF defence)", async () => {
    const f = vi.fn(async () => jsonResponse({ authenticated: false, mode: "off", name: null, roles: [] }));
    vi.stubGlobal("fetch", f);
    mount();
    await waitFor(() => expect(f).toHaveBeenCalled());
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(new Headers(init.headers).get("X-Requested-With")).toBe("spa");
  });
});
