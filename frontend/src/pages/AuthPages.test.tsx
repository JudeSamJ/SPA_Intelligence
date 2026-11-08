import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse } from "../test/helpers";
import BuyerHome from "./BuyerHome";
import Login from "./Login";
import Pending from "./Pending";
import Reset from "./Reset";
import RoleSwitch from "./RoleSwitch";
import Users from "./Users";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, "", "/"); });

const ME = { authenticated: true, mode: "supabase", name: "Ana", login: "ana@x.co", avatar_url: null };
const mount = (ui: ReactElement, url = "/") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PrefsProvider><MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter></PrefsProvider>
    </QueryClientProvider>,
  );
const bodyOf = (f: ReturnType<typeof vi.fn>, suffix: string) => {
  const c = f.mock.calls.find(([u]) => String(u).endsWith(suffix));
  return c ? JSON.parse(String((c[1] as RequestInit).body)) : undefined;
};

describe("email sign-in on the login page", () => {
  const cfg = { mode: "supabase", github: false, email: true };
  const anon = { authenticated: false, mode: "supabase", name: null, login: null, avatar_url: null, roles: [] };
  const routes = <Routes><Route path="/login" element={<Login />} /><Route path="/app/*" element={<p data-testid="in-app" />} /></Routes>;

  it("signs in with the typed email and password", async () => {
    const f = vi.fn(async (u: string, i?: RequestInit) => u.endsWith("/auth/me") ? jsonResponse(anon) : u.endsWith("/auth/config") ? jsonResponse(cfg) : jsonResponse({ authenticated: true }, i ? 200 : 200));
    vi.stubGlobal("fetch", f);
    mount(routes, "/login");
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "ana@x.co" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse-battery" } });
    fireEvent.click(screen.getByTestId("email-submit"));
    await waitFor(() => expect(bodyOf(f, "/auth/supabase/login")).toEqual({ email: "ana@x.co", password: "correct-horse-battery" }));
    expect(screen.queryByTestId("github-signin")).toBeNull();
  });

  it("shows the server's message for a wrong password", async () => {
    vi.stubGlobal("fetch", vi.fn(async (u: string) => u.endsWith("/auth/me") ? jsonResponse(anon) : u.endsWith("/auth/config") ? jsonResponse(cfg) : jsonResponse({ error: { code: "invalid", message: "Email or password is not correct." } }, 401)));
    mount(routes, "/login");
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "ana@x.co" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByTestId("email-submit"));
    expect(await screen.findByTestId("email-error")).toHaveTextContent("Email or password is not correct.");
  });

  it("creates an account and tells the person to confirm by email; also offers password reset", async () => {
    const f = vi.fn(async (u: string) => u.endsWith("/auth/me") ? jsonResponse(anon) : u.endsWith("/auth/config") ? jsonResponse(cfg) : jsonResponse({ check_email: true }, 202));
    vi.stubGlobal("fetch", f);
    mount(routes, "/login");
    fireEvent.click(await screen.findByRole("button", { name: "Create an account" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@x.co" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-enough-pass" } });
    fireEvent.click(screen.getByTestId("email-submit"));
    expect(await screen.findByTestId("email-note")).toHaveTextContent("confirm your address");
    fireEvent.click(screen.getByRole("button", { name: "I already have an account" }));
    fireEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@x.co" } });
    fireEvent.click(screen.getByTestId("email-submit"));
    await waitFor(() => expect(bodyOf(f, "/auth/supabase/recover")).toEqual({ email: "new@x.co" }));
    expect(await screen.findByTestId("email-note")).toHaveTextContent("reset link");
  });

  it("explains that the email was confirmed when the link brings them back", async () => {
    vi.stubGlobal("fetch", vi.fn(async (u: string) => u.endsWith("/auth/me") ? jsonResponse(anon) : jsonResponse(cfg)));
    mount(routes, "/login?confirmed=1");
    expect(await screen.findByTestId("email-note")).toHaveTextContent("confirmed");
  });
});

describe("what each role sees after sign-in", () => {
  const view = (roles: string[], extra: Record<string, unknown> = {}) => vi.fn(async (u: string) => {
    if (u.endsWith("/auth/me")) return jsonResponse({ ...ME, roles, ...extra });
    if (u.endsWith("/buyer/me")) return jsonResponse({ linked: true, contract_name: "sample_a.pdf" });
    return jsonResponse([]);
  });

  it("buyers get only their own contract chat, never the contract list", async () => {
    const f = view(["Spa.Buyer"]);
    vi.stubGlobal("fetch", f);
    mount(<RoleSwitch />);
    expect(await screen.findByTestId("buyer-home")).toHaveTextContent("sample_a.pdf");
    expect(f.mock.calls.some(([u]) => String(u).endsWith("/contracts"))).toBe(false);
  });

  it("people without a role see the waiting page", async () => {
    vi.stubGlobal("fetch", view([], { pending: true }));
    mount(<RoleSwitch />);
    expect(await screen.findByTestId("pending-page")).toHaveTextContent("ana@x.co");
  });

  it("Pending offers a re-check and sign-out", async () => {
    vi.stubGlobal("fetch", view([], { pending: true }));
    mount(<Pending />);
    expect(await screen.findByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});

describe("buyer chat", () => {
  it("shows an answer with its page and quote, and styles a legal refusal distinctly", async () => {
    const replies = [
      { answer: "Your handover date is 30 June 2027.", refused: false, citations: [{ tool: "handover_date", page: 3, quote: "5.1 on or before 30 June 2027" }] },
      { answer: "I can't advise on that; please contact the legal team.", refused: true, citations: [] },
    ];
    const f = vi.fn(async (u: string) => u.endsWith("/buyer/me") ? jsonResponse({ linked: true, contract_name: "c.pdf" }) : jsonResponse(replies.shift()));
    vi.stubGlobal("fetch", f);
    mount(<BuyerHome />);
    const input = await screen.findByLabelText("Ask about your contract");
    fireEvent.change(input, { target: { value: "When is handover?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const a = await screen.findByTestId("msg-assistant");
    expect(a).toHaveTextContent("30 June 2027");
    expect(a).toHaveTextContent("5.1 on or before 30 June 2027");
    expect(a).toHaveTextContent("p. 3");
    fireEvent.change(input, { target: { value: "Can I cancel?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByTestId("msg-refused")).toHaveTextContent("Referred to the legal team");
    expect(bodyOf(f, "/buyer/chat")).toMatchObject({ message: "When is handover?", channel: "web" });
  });

  it("explains when no contract is linked yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ linked: false, contract_name: null })));
    mount(<BuyerHome />);
    expect(await screen.findByText("No contract is linked to your account yet")).toBeInTheDocument();
  });
});

describe("administrator: users", () => {
  const users = [
    { user_id: "u1", email: "new@x.co", name: "", role: null, admin: false, created_at: "2026-11-08T10:00:00", last_login_at: null },
    { user_id: "u3", email: "bella@x.co", name: "", role: null, admin: false, via_assignment: true, created_at: "2026-11-08T11:00:00", last_login_at: null },
    { user_id: "u2", email: "boss@x.co", name: "Boss", role: null, admin: true, created_at: "2026-11-01T10:00:00", last_login_at: null },
  ];
  it("lists people, flags those waiting for a role, and changes a role", async () => {
    const f = vi.fn(async (_u: string, i?: RequestInit) => i?.method === "PUT" ? jsonResponse({ role: "staff" }) : jsonResponse({ users }));
    vi.stubGlobal("fetch", f);
    mount(<Users />);
    const rows = await screen.findAllByTestId("user-row");
    expect(rows[0]).toHaveTextContent("Waiting for a role");
    expect(rows[1]).toHaveTextContent("Buyer (linked to a contract)");
    expect(rows[1]).not.toHaveTextContent("Waiting for a role");
    expect(rows[2]).toHaveTextContent("Administrator");
    fireEvent.change(screen.getByLabelText("Role for new@x.co"), { target: { value: "staff" } });
    await waitFor(() => expect(f.mock.calls.some(([u, i]) => String(u).endsWith("/users/u1/role") && (i as RequestInit).method === "PUT")).toBe(true));
    expect(bodyOf(f, "/users/u1/role")).toEqual({ role: "staff" });
  });

  it("shows the server's refusal to a non-administrator", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ error: { code: "forbidden", message: "Only an administrator can do this." } }, 403)));
    mount(<Users />);
    expect(await screen.findByText("Only an administrator can do this.")).toBeInTheDocument();
  });
});

describe("password reset page", () => {
  it("reads the token from the link, hides it from the address bar and sets the new password", async () => {
    window.history.replaceState(null, "", "/reset#access_token=tok-123456789&type=recovery");
    const f = vi.fn(async () => jsonResponse({ reset: true }));
    vi.stubGlobal("fetch", f);
    mount(<Reset />, "/reset");
    expect(window.location.hash).toBe("");
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a-brand-new-password" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "different-password" } });
    expect(screen.getByText("The two passwords do not match.")).toBeInTheDocument();
    expect(screen.getByTestId("reset-submit")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a-brand-new-password" } });
    fireEvent.click(screen.getByTestId("reset-submit"));
    expect(await screen.findByText("Your password has been changed.")).toBeInTheDocument();
    expect(bodyOf(f, "/auth/supabase/reset")).toEqual({ token: "tok-123456789", password: "a-brand-new-password" });
  });

  it("explains a missing or expired link", () => {
    window.history.replaceState(null, "", "/reset");
    mount(<Reset />, "/reset");
    expect(screen.getByText(/missing or has expired/)).toBeInTheDocument();
  });
});
