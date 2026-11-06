import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderApp } from "../test/helpers";
import Assistant from "./Assistant";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => vi.unstubAllGlobals());

const ask = (text: string) => {
  fireEvent.change(screen.getByLabelText(/Ask about payments/), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
};

describe("Assistant", () => {
  it("styles legal-advice refusals distinctly and shows the legal-team referral", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          answer: "I can't advise on that; please contact the legal team.",
          refused: true,
          citations: [],
          tool_calls: [],
        }),
      ),
    );
    renderApp(<Assistant />);
    ask("can I cancel and get a refund?");
    const refused = await screen.findByTestId("msg-refused");
    expect(refused).toHaveTextContent("please contact the legal team");
    expect(refused).toHaveTextContent("Referred to the legal team");
    expect(screen.queryByTestId("msg-assistant")).toBeNull();
  });

  it("renders answers as plain text (no HTML injection) with a clickable page citation", async () => {
    const evil = "Handover <img src=x onerror=alert(1)> is 30 June 2027";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          answer: evil,
          refused: false,
          citations: [{ tool: "handover_date", page: 3, quote: "30 June 2027" }],
          tool_calls: ["handover_date"],
        }),
      ),
    );
    renderApp(<Assistant />);
    ask("When is handover?");
    const msg = await screen.findByTestId("msg-assistant");
    await waitFor(() => expect(msg).toHaveTextContent(evil));
    expect(msg.querySelector("img")).toBeNull();
    const cite = screen.getByTestId("citation");
    expect(cite).toHaveTextContent("Page 3");
    expect(cite).toHaveTextContent("30 June 2027");
  });

  it("shows the API error message when the assistant fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ error: { code: "llm_unavailable", message: "Azure returned 404" } }, 503),
        ),
    );
    renderApp(<Assistant />);
    ask("What is the handover date?");
    expect(await screen.findByText(/Azure returned 404/)).toBeInTheDocument();
  });
});
