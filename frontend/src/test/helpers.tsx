import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { ContractCtx } from "../pages/ctx";
import type { ContractDetail } from "../api/client";

export const sourced = <T,>(value: T | null, page: number | null = 1, quote: string | null = "q") => ({
  value,
  source_page: page,
  source_quote: quote,
});

export const detail = (over: Partial<ContractDetail["contract"]> = {}): ContractDetail => ({
  id: "a".repeat(64),
  name: "sample_a.pdf",
  pdf_url: "/api/contracts/x/pdf",
  contract: {
    buyer: sourced("Layla"),
    unit_id: sourced("MCR-1204"),
    price: sourced(2450000),
    area_sqft: sourced(1180),
    handover_date: sourced("2027-06-30", 3, "30 June 2027"),
    grace_period_days: sourced(60, 3),
    delay_rate: sourced(6, 3),
    delay_basis: sourced("percent_per_annum", 3),
    delay_cap: sourced(10, 3),
    payment_plan: [],
    cancellation_clause: sourced("x", 4),
    warnings: [],
    payment_plan_percent_sum: 100,
    extracted_at: "2026-01-01T00:00:00",
    model: "m",
    ...over,
  } as ContractDetail["contract"],
  plan: [],
});

export function renderApp(ui: ReactElement, d: ContractDetail = detail()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PrefsProvider>
        <MemoryRouter>
          <ContractCtx.Provider value={{ id: d.id, detail: d, openPdf: () => {} }}>{ui}</ContractCtx.Provider>
        </MemoryRouter>
      </PrefsProvider>
    </QueryClientProvider>,
  );
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
