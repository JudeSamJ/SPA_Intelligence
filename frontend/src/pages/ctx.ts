import { createContext, useContext } from "react";
import type { ContractDetail } from "../api/client";

export interface ContractCtxValue {
  id: string;
  detail: ContractDetail;
  /** open the PDF side panel at a page (and scroll it into view) */
  openPdf: (page: number) => void;
}
export const ContractCtx = createContext<ContractCtxValue | null>(null);
export function useContractCtx(): ContractCtxValue {
  const v = useContext(ContractCtx);
  if (!v) throw new Error("useContractCtx must be used inside ContractLayout");
  return v;
}
