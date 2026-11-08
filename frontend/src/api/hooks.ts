import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ChatTurn, type ContractSummary } from "./client";
import { apiX } from "./trust";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000 });

export const useContracts = () =>
  useQuery({
    queryKey: ["contracts"],
    queryFn: api.contracts,
    refetchInterval: (q) => {
      const rows = q.state.data as ContractSummary[] | undefined;
      return rows?.some((c) => c.status === "queued" || c.status === "ocr" || c.status === "running") ? 1200 : false;
    },
  });

export const useContract = (id: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ["contract", id],
    queryFn: () => api.contract(id!),
    enabled: !!id && enabled,
    retry: false,
  });

export const useStatus = (id: string | undefined, poll: boolean) =>
  useQuery({
    queryKey: ["status", id],
    queryFn: () => api.status(id!),
    enabled: !!id && poll,
    refetchInterval: 1000,
  });

export function useExtract(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => api.extract(id, force),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["contracts"] }),
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.upload(file),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["contracts"] }),
  });
}

export const usePenalty = (id: string | undefined, scenarios?: number[]) =>
  useQuery({
    queryKey: ["penalty", id, scenarios ?? "default"],
    queryFn: () => api.penalty(id!, scenarios),
    enabled: !!id,
    retry: false,
    placeholderData: keepPreviousData,
  });

export const useCashflow = (id: string | undefined, granularity: "month" | "quarter", delay?: number) =>
  useQuery({
    queryKey: ["cashflow", id, granularity, delay ?? "default"],
    queryFn: () => api.cashflow(id!, granularity, delay),
    enabled: !!id,
    retry: false,
    placeholderData: keepPreviousData,
  });

export const useChat = (id: string) =>
  useMutation({
    mutationFn: (v: { message: string; history: ChatTurn[] }) => api.chat(id, v.message, v.history),
  });

export const useEvalResults = () => useQuery({ queryKey: ["eval"], queryFn: api.evalResults, retry: false });

export function useEvalRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (allow: boolean) => api.evalRun(allow),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["evalStatus"] }),
  });
}

export const useEvalStatus = (enabled: boolean) =>
  useQuery({
    queryKey: ["evalStatus"],
    queryFn: api.evalStatus,
    enabled,
    refetchInterval: (q) => (q.state.data?.state === "running" ? 800 : false),
  });

export const usePacks = () => useQuery({ queryKey: ["packs"], queryFn: apiX.packs, staleTime: 600_000 });
