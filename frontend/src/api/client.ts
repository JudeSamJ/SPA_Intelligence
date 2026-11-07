import { getToken } from "../auth/token";
import type { components } from "./types";

type S = components["schemas"];
export type ContractSummary = S["ContractSummary"];
export type ContractStatus = S["ContractStatus"];
export type ContractDetail = S["ContractDetail"];
export type ContractData = S["ContractData"];
export type PlanRow = S["PlanRow"];
export type PenaltyResponse = S["PenaltyResponse"];
export type PenaltyRow = S["PenaltyRow"];
export type CashflowResponse = S["CashflowResponse"];
export type Period = S["Period"];
export type ChatResponse = S["ChatResponse"];
export type ChatTurn = S["ChatTurn"];
export type Citation = S["Citation"];
export type EvalResults = S["EvalResults"];
export type EvalRunStatus = S["EvalRunStatus"];
export type Health = S["Health"];

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const token = await getToken();
    const headers = new Headers(init?.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    headers.set("X-Requested-With", "spa"); // CSRF defence for cookie sessions: a cross-site page cannot set this without a preflight
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "Could not reach the server.");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status}).`;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      if (body.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch {
      /* non-JSON error body: keep defaults */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/health"),
  contracts: () => request<ContractSummary[]>("/contracts"),
  contract: (id: string) => request<ContractDetail>(`/contracts/${id}`),
  status: (id: string) => request<ContractStatus>(`/contracts/${id}/status`),
  extract: (id: string, force = false) =>
    request<ContractStatus>(`/contracts/${id}/extract?force=${force}`, { method: "POST" }),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<ContractStatus>("/contracts/upload", { method: "POST", body: fd });
  },
  pdfUrl: (id: string, page?: number) => `${BASE}/contracts/${id}/pdf${page ? `#page=${page}` : ""}`,
  penalty: (id: string, scenarios?: number[]) =>
    request<PenaltyResponse>(`/contracts/${id}/penalty`, json({ scenarios: scenarios ?? null })),
  cashflow: (id: string, granularity: "month" | "quarter", delay_days?: number) =>
    request<CashflowResponse>(
      `/contracts/${id}/cashflow`,
      json({ granularity, delay_days: delay_days ?? null }),
    ),
  chat: (id: string, message: string, history: ChatTurn[]) =>
    request<ChatResponse>(`/contracts/${id}/chat`, json({ message, history })),
  evalResults: () => request<EvalResults>("/eval/results"),
  evalRun: (allow_llm: boolean) => request<EvalRunStatus>("/eval/run", json({ allow_llm, use_cache: true })),
  evalStatus: () => request<EvalRunStatus>("/eval/run/status"),
};
