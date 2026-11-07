import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse, renderApp } from "../test/helpers";
import Gap from "../pages/Gap";
import { GroundingChip } from "./GroundingChip";
import { PageViewer } from "./PageViewer";
import { UnreviewedBadge } from "./UnreviewedBadge";

vi.mock("../motion/registry", async () => (await import("../test/gsapMock")).default);
vi.mock("@gsap/react", () => ({ useGSAP: () => {} }));
afterEach(() => vi.unstubAllGlobals());

describe("PageViewer", () => {
  it("places highlight rectangles as percentages of the page size", () => {
    render(
      <PrefsProvider>
        <PageViewer src="x.png" page={2} label="page" evidence={{ page: 2, rects: [[59.5, 100, 119, 120]], page_width: 595, page_height: 842 }} />
      </PrefsProvider>,
    );
    fireEvent.load(screen.getByRole("img"));
    const h = screen.getByTestId("highlight");
    expect(h.style.left).toBe("10%");
    expect(h.style.width).toBe("10%");
    expect(parseFloat(h.style.top)).toBeCloseTo((100 / 842) * 100, 3);
  });
  it("draws nothing for evidence on a different page", () => {
    render(
      <PrefsProvider>
        <PageViewer src="x.png" page={1} label="page" evidence={{ page: 2, rects: [[1, 1, 2, 2]], page_width: 100, page_height: 100 }} />
      </PrefsProvider>,
    );
    fireEvent.load(screen.getByRole("img"));
    expect(screen.queryByTestId("highlight")).toBeNull();
  });
});

describe("badges", () => {
  it("shows the unreviewed-legal-logic badge text", () => {
    renderApp(<UnreviewedBadge />);
    expect(screen.getByTestId("unreviewed-badge")).toHaveTextContent("Unreviewed legal logic");
  });
  it("grounding chip: human verified wins over the grounding status", () => {
    renderApp(<GroundingChip item={{ grounding: { status: "ungrounded" }, human_verified: true, confidence: 0.2 }} />);
    expect(screen.getByTestId("grounding-chip")).toHaveAttribute("data-status", "human");
  });
});

const gap = (over = {}) => ({
  can_compute: true, jurisdiction: "in_rera", currency: "INR", unreviewed: true, one_sided: true, shortfall: 380000.5,
  entry: { statute: "RERA", section: "Section 18(1)", description: "d", source_url: "TODO", reviewed_by_lawyer: false, needs_legal_review: false, unreviewed: true, id: "x", effective_from: null },
  statutory: { amount: 400000.25, payments: [], spread_pct: 2, rate_table: { id: "t", name: "T", illustrative: true, source: "", rows: [] } },
  contractual: { penalty: 19999.75, cap_reached: false, cap_amount: null, chargeable_days: 90 },
  inputs: [{ label: "Purchase price", value: 8450000, field: "price", source: "contract" }],
  findings: [{ code: "delay_compensation_below_statute", severity: "high", field: "delay_rate", message: "below statute", evidence_fields: ["delay_rate"] }],
  evidence: { delay_rate: { page: 4, quote: "q", has_box: true }, price: { page: 3, quote: "p", has_box: true } },
  ...over,
});

describe("Gap tab", () => {
  it("shows both amounts, the exact shortfall, the unreviewed badge, illustrative-rate warning and evidence links", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(gap())));
    renderApp(<Gap />);
    await waitFor(() => expect(screen.getByTestId("gap-shortfall")).toHaveTextContent("AED 380,000.50"));
    expect(screen.getByTestId("gap-contract")).toHaveTextContent("19,999.75");
    expect(screen.getByTestId("gap-statute")).toHaveTextContent("400,000.25");
    expect(screen.getAllByTestId("unreviewed-badge").length).toBeGreaterThan(0);
    expect(screen.getByTestId("illustrative-rates")).toBeInTheDocument();
    expect(screen.getAllByTestId("evidence-link").length).toBeGreaterThanOrEqual(2);
  });
  it("shows a clear 'cannot compute' reason instead of a number", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ can_compute: false, reason: "no rate in effect", jurisdiction: "in_rera", needs_legal_review: true })));
    renderApp(<Gap />);
    await waitFor(() => expect(screen.getByTestId("gap-cannot")).toHaveTextContent("no rate in effect"));
    expect(screen.queryByTestId("gap-shortfall")).toBeNull();
    expect(screen.getByTestId("unreviewed-badge")).toBeInTheDocument();
  });
});
