import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse } from "../test/helpers";
import Login from "./Login";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => vi.unstubAllGlobals());

const api = (me: object, cfg: object = { mode: "apikey", github: true }) =>
  vi.fn(async (u: string) =>
    u.endsWith("/auth/me")
      ? jsonResponse({ authenticated: false, mode: "apikey", name: null, login: null, avatar_url: null, roles: [], ...me })
      : jsonResponse(cfg),
  );

const mount = (url = "/login") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PrefsProvider>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/app/*" element={<p data-testid="in-app">in the app</p>} />
          </Routes>
        </MemoryRouter>
      </PrefsProvider>
    </QueryClientProvider>,
  );

describe("Login page", () => {
  it("offers GitHub sign-in that carries the destination", async () => {
    vi.stubGlobal("fetch", api({}));
    mount("/login?next=%2Fapp%2Fcontracts%2Fabc%2Fgap");
    const a = await screen.findByTestId("github-signin");
    expect(a).toHaveAttribute("href", "/api/auth/github/login?next=%2Fapp%2Fcontracts%2Fabc%2Fgap");
    expect(screen.getByText(/approved GitHub accounts/i)).toBeInTheDocument();
  });

  it("never carries an outside destination (open-redirect defence)", async () => {
    vi.stubGlobal("fetch", api({}));
    mount("/login?next=https%3A%2F%2Fevil.example");
    expect(await screen.findByTestId("github-signin")).toHaveAttribute("href", "/api/auth/github/login?next=%2Fapp");
  });

  it("explains a refused account by name, and other failures", async () => {
    vi.stubGlobal("fetch", api({}));
    mount("/login?error=not_allowed&login=stranger");
    expect(await screen.findByTestId("login-error")).toHaveTextContent('"stranger" is not allowed');
  });

  it("ignores an unknown error code instead of printing it", async () => {
    vi.stubGlobal("fetch", api({}));
    mount("/login?error=<script>x</script>");
    await screen.findByTestId("github-signin");
    expect(screen.queryByTestId("login-error")).toBeNull();
  });

  it("goes straight to the app when already signed in, or when server auth is off", async () => {
    vi.stubGlobal("fetch", api({ authenticated: true, name: "Alice" }));
    mount();
    await waitFor(() => expect(screen.getByTestId("in-app")).toBeInTheDocument());
  });

  it("says sign-in is not configured when GitHub is not set up", async () => {
    vi.stubGlobal("fetch", api({}, { mode: "apikey", github: false }));
    mount();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not configured/i));
    expect(screen.queryByTestId("github-signin")).toBeNull();
  });
});
