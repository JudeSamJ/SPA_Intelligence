import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse } from "../test/helpers";
import { AuthGate } from "./AuthGate";

afterEach(() => vi.unstubAllGlobals());

const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().search}</p>;
const mount = (start = "/app/contracts/abc/gap") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PrefsProvider>
        <MemoryRouter initialEntries={[start]}>
          <Routes>
            <Route path="/login" element={<Where />} />
            <Route
              path="/app/*"
              element={
                <AuthGate>
                  <p>the app</p>
                </AuthGate>
              }
            />
          </Routes>
        </MemoryRouter>
      </PrefsProvider>
    </QueryClientProvider>,
  );

const me = (over: object) =>
  vi.fn(async () => jsonResponse({ authenticated: false, mode: "off", name: null, login: null, avatar_url: null, roles: [], ...over }));

describe("AuthGate", () => {
  it("shows the app unchanged when server authentication is off", async () => {
    vi.stubGlobal("fetch", me({}));
    mount();
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
  });

  it("sends a visitor who is not signed in to the login page, remembering where they were going", async () => {
    vi.stubGlobal("fetch", me({ mode: "apikey", authenticated: false }));
    mount();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login?next=%2Fapp%2Fcontracts%2Fabc%2Fgap"));
    expect(screen.queryByText("the app")).toBeNull();
  });

  it("shows the app once signed in", async () => {
    vi.stubGlobal("fetch", me({ mode: "apikey", authenticated: true, name: "Alice A", roles: ["Spa.Reviewer"] }));
    mount();
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
  });

  it("sends X-Requested-With on every API call (CSRF defence)", async () => {
    const f = me({});
    vi.stubGlobal("fetch", f);
    mount();
    await waitFor(() => expect(f).toHaveBeenCalled());
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(new Headers(init.headers).get("X-Requested-With")).toBe("spa");
  });
});
