import { createContext, useContext } from "react";
import type { ContractDetail } from "../api/client";

/** What to highlight in the PDF panel: a named field (exact box from the server) or any page + quote. */
export interface EvidenceTarget {
  field?: string;
  page?: number;
  quote?: string | null;
}

export interface ContractCtxValue {
  id: string;
  detail: ContractDetail;
  /** open the PDF side panel at a page (and scroll it into view) */
  openPdf: (page: number) => void;
  /** open the PDF side panel with the exact span highlighted */
  openEvidence: (t: EvidenceTarget) => void;
}
export const ContractCtx = createContext<ContractCtxValue | null>(null);
export function useContractCtx(): ContractCtxValue {
  const v = useContext(ContractCtx);
  if (!v) throw new Error("useContractCtx must be used inside ContractLayout");
  return v;
}
