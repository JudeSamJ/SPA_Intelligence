import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderApp } from "../test/helpers";
import Penalty from "./Penalty";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => vi.unstubAllGlobals());

const q = (v: number, p = 1) => ({ value: v, source_page: p, source_quote: "6% per annum" });
const row = (d: number, pen: number) => ({
  delay_days: d,
  grace_days: 30,
  chargeable_days: Math.max(0, d - 30),
  penalty: pen,
  cap_amount: null,
  cap_reached: false,
  pct_of_price: pen / 10000,
});
const body = (scen: number[]) => ({
  terms: {
    rate: q(6),
    basis: { value: "percent_per_annum", source_page: 3, source_quote: "q" },
    grace_days: q(30),
    cap_pct: { value: null, source_page: null, source_quote: null },
    price: q(1000000),
    area_sqft: q(1000),
  },
  day_count_basis: 365,
  default_scenarios: [30, 90, 180, 365],
  rows: scen.map((d) => row(d, d === 90 ? 9863.01 : d === 180 ? 29589.04 : 0)),
});

describe("Penalty tab renders exactly what the API returns", () => {
  it("shows the 9,863.01 scenario row and no locally computed amounts", async () => {
    const f = vi.fn(async (_u: string, init?: RequestInit) => {
      const b = JSON.parse((init?.body as string) ?? "{}") as { scenarios: number[] | null };
      return jsonResponse(body(b.scenarios ?? [30, 90, 180, 365]));
    });
    vi.stubGlobal("fetch", f);
    renderApp(<Penalty />);
    await waitFor(() => expect(screen.getByTestId("scenario-90")).toHaveTextContent("AED 9,863.01"));
    expect(screen.getByTestId("scenario-30")).toHaveTextContent("AED 0.00");
    await waitFor(() => expect(screen.getByTestId("penalty-amount")).toHaveTextContent("AED 29,589.04")); // dial starts on the 180-day preset
    expect(screen.getAllByTestId("scenario-row")).toHaveLength(4);
  });

  it("shows the server's explanation when the contract cannot be simulated", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "simulation_unavailable", message: "Delay basis is 'other'." } },
            422,
          ),
        ),
    );
    renderApp(<Penalty />);
    expect(await screen.findByText("Delay basis is 'other'.")).toBeInTheDocument();
  });
});
