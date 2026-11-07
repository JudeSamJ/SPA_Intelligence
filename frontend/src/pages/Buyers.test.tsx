import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderApp } from "../test/helpers";
import Buyers from "./Buyers";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => vi.unstubAllGlobals());

const A = "a".repeat(64);
const contracts = [{ id: A, name: "sample_a.pdf", kind: "sample", pages: 6, status: "extracted", needs_review: 0 }];
const row = { id: 7, contract_id: A, identity: "buyer@example.com", channel: "teams", active: true, created_by: "Rita", created_at: "2026-11-07T10:00:00" };

function stub(assignments: unknown[], post?: () => Response) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/contracts")) return Promise.resolve(jsonResponse(contracts));
    if (u.endsWith("/buyers") && init?.method === "POST") return Promise.resolve(post ? post() : jsonResponse(row, 201));
    if (u.includes("/buyers/") && init?.method === "DELETE") return Promise.resolve(jsonResponse({ removed: 7 }));
    if (u.endsWith("/buyers")) return Promise.resolve(jsonResponse({ assignments }));
    return Promise.resolve(jsonResponse({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Buyers", () => {
  it("lists linked buyers with their contract, channel and who added them", async () => {
    stub([row]);
    renderApp(<Buyers />);
    const r = await screen.findByTestId("buyer-row");
    expect(r).toHaveTextContent("buyer@example.com");
    expect(r).toHaveTextContent("sample_a.pdf");
    expect(r).toHaveTextContent("Teams");
    expect(r).toHaveTextContent("Added by Rita");
  });

  it("shows an empty state, and the add button stays disabled until an identity is typed", async () => {
    stub([]);
    renderApp(<Buyers />);
    expect(await screen.findByText("No buyers are linked yet.")).toBeInTheDocument();
    expect(screen.getByTestId("buyer-add")).toBeDisabled();
  });

  it("sends the chosen contract, trimmed identity and channel", async () => {
    const f = stub([]);
    renderApp(<Buyers />);
    await screen.findByText("No buyers are linked yet.");
    fireEvent.change(screen.getByLabelText("Email or phone"), { target: { value: "  new@buyer.co " } });
    fireEvent.change(screen.getByLabelText("Channel"), { target: { value: "whatsapp" } });
    fireEvent.click(screen.getByTestId("buyer-add"));
    await waitFor(() => expect(f.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true));
    const post = f.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ contract_id: A, identity: "new@buyer.co", channel: "whatsapp" });
  });

  it("shows the server's message when linking fails, and removes a buyer", async () => {
    const f = stub([row], () => jsonResponse({ error: { code: "buyer_error", message: "That buyer is already assigned to a different contract." } }, 409));
    renderApp(<Buyers />);
    await screen.findByTestId("buyer-row");
    fireEvent.change(screen.getByLabelText("Email or phone"), { target: { value: "x@y.co" } });
    fireEvent.click(screen.getByTestId("buyer-add"));
    expect(await screen.findByRole("alert")).toHaveTextContent("already assigned");
    fireEvent.click(screen.getByTestId("buyer-remove"));
    await waitFor(() => expect(f.mock.calls.some(([u, i]) => String(u).endsWith("/buyers/7") && (i as RequestInit).method === "DELETE")).toBe(true));
  });
});
