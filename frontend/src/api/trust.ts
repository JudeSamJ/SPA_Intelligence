/** Hand-typed shapes for the Phase 1-3 endpoints (the OpenAPI schema types them loosely as dicts). */
import { json, request } from "./client";

export interface Evidence {
  page?: number | null;
  quote?: string | null;
  bbox?: number[] | null;
  rects: number[][];
  page_width?: number | null;
  page_height?: number | null;
  method?: string | null;
}
export interface EvidenceResponse {
  field: string;
  value: unknown;
  evidence: Evidence;
  grounding_status?: string | null;
  confidence?: number | null;
  human_verified: boolean;
}
export interface PackEntry {
  id: string;
  statute: string;
  section: string;
  description: string;
  effective_from: string | null;
  source_url: string;
  reviewed_by_lawyer: boolean;
  needs_legal_review: boolean;
  unreviewed: boolean;
}
export interface Pack {
  id: string;
  name: string;
  country: string;
  currency: string;
  version: string;
  entries: PackEntry[];
}
export interface GapInput {
  label: string;
  value: unknown;
  field: string | null;
  source: string;
}
export interface GapFinding {
  code: string;
  severity: "high" | "medium" | "low";
  field: string;
  message: string;
  evidence_fields: string[];
}
export interface GapPayment {
  date: string;
  amount: number;
  label: string;
  counted: boolean;
  days: number;
  interest: number;
  accrues_from?: string;
  note?: string;
  field?: string | null;
  segments?: { from: string; to: string; days: number; base_pct: number; rate_pct: number; interest: number }[];
}
export interface GapResult {
  can_compute: boolean;
  reason?: string;
  jurisdiction: string;
  currency?: string;
  needs_legal_review?: boolean;
  entry?: PackEntry | null;
  delay_days?: number;
  as_of?: string;
  possession_date?: string;
  amounts_paid_source?: "user" | "payment_plan";
  amounts_paid_total?: number;
  statutory?: {
    amount: number;
    payments: GapPayment[];
    spread_pct: number;
    rate_table: { id: string; name: string; illustrative: boolean; source: string; rows: { effective_from: string; rate_pct: number }[] };
  };
  contractual?: { penalty: number; cap_reached: boolean; cap_amount: number | null; chargeable_days: number } | null;
  contractual_reason?: string | null;
  shortfall?: number | null;
  one_sided?: boolean | null;
  unreviewed?: boolean;
  inputs?: GapInput[];
  findings?: GapFinding[];
  evidence?: Record<string, { page: number | null; quote: string | null; has_box: boolean }>;
  note?: string;
}
export interface PaidRow {
  date: string;
  amount: number;
  label?: string;
}
export interface Summary {
  p10: number;
  p50: number;
  p90: number;
  mean: number;
}
export interface MCResult {
  assumption_driven: boolean;
  label: string;
  trials: number;
  seed: number;
  jurisdiction: string;
  currency: string | null;
  assumptions: { delay_distribution: Record<string, unknown>; signal: null | { shift_days: number; gap_points: number; rule: string; clamped: boolean }; as_of: string; grace_days: number; cap_pct: number | null };
  delay_days: Summary;
  prob_delay_exceeds_grace: number;
  prob_cap_binds: number | null;
  contractual: Summary | null;
  statutory: Summary | null;
  shortfall: Summary | null;
  unavailable_reason: string | null;
  histogram: { from: number; to: number; count: number }[];
  quantiles: { q: number; delay: number; contractual: number | null; statutory: number | null }[];
}
export interface MCPortfolio {
  label: string;
  trials: number;
  rows: { contract_id: string; name: string; currency: string | null; contractual: Summary | null; statutory: Summary | null; shortfall: Summary | null; prob_cap_binds: number | null; unavailable_reason: string | null }[];
  totals_by_currency: Record<string, { contracts: number; contracts_with_statute: number; contractual: Summary | null; statutory: Summary | null; shortfall: Summary | null }>;
  note: string;
}
export interface MCRequest {
  trials?: number;
  seed?: number;
  family?: "triangular" | "lognormal" | "fixed";
  params?: Record<string, number>;
  as_of_date?: string;
  signal_csv?: string;
}
export interface Obligation {
  id: string;
  contract_id: string;
  contract_name: string;
  kind: string;
  label: string;
  due_date: string;
  days_until: number;
  amount: number | null;
  currency: string | null;
  event_type: string | null;
  status: string;
  severity: "high" | "medium" | "low" | "none";
  field: string;
  evidence: { page: number | null; quote: string | null };
  assumed_anchor: string | null;
}
export interface Alert {
  id: string;
  contract_id: string;
  contract_name: string;
  event_type: string;
  severity: "high" | "medium" | "low";
  message: string;
  due_date: string;
  acked: boolean;
  field: string;
  evidence: { page: number | null; quote: string | null };
}
export interface ReviewItem {
  contract_id: string;
  contract_name: string;
  field: string;
  value: unknown;
  claimed_value: string | null;
  status: string;
  confidence: number | null;
  source_page: number | null;
  source_quote: string | null;
  reasons: string[];
}
export interface EvalRunSummary {
  run_id: string;
  timestamp: string;
  engine: string;
  model: string;
  git_commit: string | null;
  stub: boolean;
  golden: { size: number; synthetic: number; real: number };
  overall: { precision: number | null; recall: number | null; f1: number | null; grounding_pass_rate: number | null; abstention_rate: number | null; hallucinations: number };
  table: { row_f1: number | null; sum_correct: number; docs: number };
  regressions: number;
  compared_to: string | null;
}
export interface EvalRunDetail extends EvalRunSummary {
  fields: Record<string, { precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; fn: number }>;
  regressions: { metric: string; before: number; after: number }[] & number;
}
export interface Bakeoff {
  golden_size: number;
  golden_real: number;
  note: string;
  engines: {
    name: string;
    description: string;
    configured: boolean;
    reason: string;
    run: null | (EvalRunSummary & { fields: Record<string, number | null>; avg_latency_s: number | null; input_tokens: number; output_tokens: number; cost_per_doc_usd: number | null; cached_docs: number });
  }[];
}
export interface CrossFact {
  doc_id: string;
  doc_type: string;
  raw: unknown;
  shown: string;
  page: number | null;
  quote: string | null;
  locator: { file: string; row: number; column: string } | null;
  field: string | null;
}
export interface CrossConflict {
  attribute: string;
  label: string;
  severity: "high" | "medium" | "low";
  uncertain_match: boolean;
  values: CrossFact[];
  explanation: string;
}
export interface CrossResult {
  set_id: string;
  unit_key: string;
  kind: string;
  synthetic: boolean;
  documents: { id: string; type: string; name: string; match: string; score?: number; unit_text?: string; facts: number; note?: string | null }[];
  pending: string[];
  pending_note?: string;
  conflicts: CrossConflict[];
  agreements: { attribute: string; label: string; documents: string[] }[];
  graph: { nodes: { id: string; type: string; label: string; attribute?: string; doc_id?: string; conflict: boolean; page?: number; quote?: string; field?: string; match?: string }[]; edges: { source: string; target: string; kind: string }[] };
  planted?: { attribute: string; docs: string[] }[] | null;
  planted_score?: { tp: number; fp: number; fn: number; precision: number; recall: number };
  llm_calls_made: number;
}
export interface PlaybookRow {
  rule_id: string;
  kind: "deterministic" | "qualitative";
  clause_type: string | null;
  title: string;
  status: "pass" | "fail" | "needs_review" | "not_run";
  severity: string;
  reason: string;
  confidence: number | null;
  evidence: Evidence | null;
  suggestion: null | {
    available: boolean;
    flag?: string;
    text?: string;
    version?: string;
    approved_by?: string;
    status?: string;
    file?: string;
    redline?: { op: string; old: string; new: string }[] | null;
  };
}
export interface PlaybookResult {
  playbook_version: string;
  playbook_status: string;
  jurisdiction: string;
  results: PlaybookRow[];
  summary: Record<string, number>;
  llm_run: boolean;
}
export interface ErpResult {
  mode: string;
  entity: string;
  placeholder_mapping: boolean;
  mapping_note: string;
  rows: Record<string, unknown>[];
  row_count: number;
  errors: { row: number; field: string; source: string; error: string }[];
  valid: boolean;
  csv: string;
  push_enabled: boolean;
}

const q = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const apiX = {
  evidence: (id: string, field: string) => request<EvidenceResponse>(`/contracts/${id}/evidence/${field}`),
  locate: (id: string, page: number, quote: string) => request<Evidence>(`/contracts/${id}/locate${q({ page, quote })}`),
  pageUrl: (id: string, page: number, scale = 1.5) => `${import.meta.env.VITE_API_BASE ?? "/api"}/contracts/${id}/page/${page}.png${q({ scale })}`,
  setJurisdiction: (id: string, jurisdiction: string | null) =>
    request<{ jurisdiction: string }>(`/contracts/${id}/jurisdiction`, { ...json({ jurisdiction }), method: "PUT" }),
  packs: () => request<{ packs: Pack[] }>("/packs"),
  gap: (id: string, body: { delay_days: number; as_of_date?: string; amounts_paid?: PaidRow[]; jurisdiction?: string }) =>
    request<GapResult>(`/contracts/${id}/statute-gap`, json(body)),
  mc: (id: string, body: MCRequest) => request<MCResult>(`/contracts/${id}/montecarlo`, json(body)),
  mcPortfolio: (body: MCRequest) => request<MCPortfolio>("/portfolio/montecarlo", json(body)),
  mcDefaults: () => request<{ trials: number; seed: number; delay_distribution: Record<string, Record<string, number> & { family?: string }> & { family: string }; signal: { days_per_gap_point: number; max_shift_days: number } }>("/simulation/defaults"),
  obligations: (p: { as_of?: string; within_days?: number; status?: string; contract_id?: string }) =>
    request<{ as_of: string; obligations: Obligation[]; event_types: string[]; caveat: string }>(`/obligations${q(p)}`),
  alerts: (includeAcked = false) => request<{ alerts: Alert[]; unacked: number; delivery: string }>(`/alerts${q({ include_acked: includeAcked })}`),
  recompute: (as_of?: string) => request<{ alerts: number; new: number }>(`/alerts/recompute${q({ as_of })}`, { method: "POST" }),
  ack: (id: string) => request<Alert>(`/alerts/${id}/ack`, { method: "POST" }),
  reviewQueue: () => request<{ items: ReviewItem[]; count: number }>("/review-queue"),
  review: (id: string, field: string, body: { action: "accept" | "correct" | "reject"; value?: unknown; note?: string; reviewer?: string }) =>
    request<{ saved: unknown }>(`/contracts/${id}/fields/${field}/review`, json(body)),
  goldenExport: (id: string, allowPartial = false) =>
    request<{ path: string; doc_id: string }>(`/contracts/${id}/golden-export${q({ allow_partial: allowPartial })}`, { method: "POST" }),
  runs: (engine?: string) => request<{ runs: EvalRunSummary[] }>(`/eval/runs${q({ engine })}`),
  run: (id: string) => request<EvalRunDetail>(`/eval/runs/${id}`),
  bakeoff: () => request<Bakeoff>("/eval/bakeoff"),
  evalRunEngine: (engine: string, allow_llm: boolean) => request<{ state: string }>("/eval/run", json({ allow_llm, use_cache: true, engine })),
  crossSets: () => request<{ sets: { set_id: string; kind: string; unit_key: string; documents: string[]; synthetic: boolean; planted: number | null }[] }>("/crossdoc/sets"),
  cross: (setId: string, extract: boolean) => request<CrossResult>(`/crossdoc/sets/${setId}${q({ extract })}`),
  crossPageUrl: (setId: string, docId: string, page: number) => `${import.meta.env.VITE_API_BASE ?? "/api"}/crossdoc/sets/${setId}/documents/${docId}/page/${page}.png`,
  crossEvidence: (setId: string, docId: string, page: number, quote: string) =>
    request<Evidence>(`/crossdoc/sets/${setId}/documents/${docId}/evidence${q({ page, quote })}`),
  playbook: (id: string, runLlm: boolean) => request<PlaybookResult>(`/contracts/${id}/playbook${q({ run_llm: runLlm })}`),
  playbookCsvUrl: (id: string) => `${import.meta.env.VITE_API_BASE ?? "/api"}/contracts/${id}/playbook${q({ format: "csv" })}`,
  erpExport: (id: string, body: { delay_days?: number; as_of_date?: string }) => request<ErpResult>(`/contracts/${id}/erp/export`, json(body)),
  erpPush: (id: string, body: { delay_days?: number; as_of_date?: string; confirm: boolean; reviewer?: string }) =>
    request<{ pushed: number; rows: number }>(`/contracts/${id}/erp/push`, json(body)),
};
