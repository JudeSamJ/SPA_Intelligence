import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiX } from "../api/trust";
import { useContracts } from "../api/hooks";
import { Alert, EmptyState, Skeleton } from "../components/ui";

const CHANNELS = ["any", "teams", "whatsapp", "web", "email", "api"] as const;

export default function Buyers() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const contracts = useContracts();
  const list = useQuery({ queryKey: ["buyers"], queryFn: apiX.buyers, retry: false });
  const [contractId, setContractId] = useState("");
  const [identity, setIdentity] = useState("");
  const [channel, setChannel] = useState<string>("any");
  const names = new Map((contracts.data ?? []).map((c) => [c.id, c.name]));
  const refresh = () => void qc.invalidateQueries({ queryKey: ["buyers"] });
  const add = useMutation({
    mutationFn: () => apiX.assignBuyer({ contract_id: contractId || (contracts.data?.[0]?.id ?? ""), identity: identity.trim(), channel }),
    onSuccess: () => { setIdentity(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: number) => apiX.removeBuyer(id), onSuccess: refresh });
  const options = contracts.data ?? [];
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 8 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("buyers.title")}</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("buyers.intro")}</p>
      </section>

      <form
        className="card"
        style={{ padding: "1rem", display: "grid", gap: 10 }}
        onSubmit={(e) => { e.preventDefault(); add.mutate(); }}
        data-testid="buyer-form"
      >
        {options.length === 0 && !contracts.isLoading ? (
          <Alert tone="info">{t("buyers.noContracts")}</Alert>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}>
            <label style={{ display: "grid", gap: 4, flex: "1 1 220px" }}>
              <span>{t("buyers.contract")}</span>
              <select value={contractId || options[0]?.id || ""} onChange={(e) => setContractId(e.target.value)} style={{ minHeight: 44 }}>
                {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ display: "grid", gap: 4, flex: "1 1 240px" }}>
              <span>{t("buyers.identity")}</span>
              <input value={identity} onChange={(e) => setIdentity(e.target.value)} dir="ltr" inputMode="email" autoComplete="off" style={{ minHeight: 44 }} />
            </label>
            <label style={{ display: "grid", gap: 4, flex: "0 1 160px" }}>
              <span>{t("buyers.channel")}</span>
              <select value={channel} onChange={(e) => setChannel(e.target.value)} style={{ minHeight: 44 }}>
                {CHANNELS.map((c) => <option key={c} value={c}>{t(`buyers.channels.${c}`)}</option>)}
              </select>
            </label>
            <button className="btn" type="submit" disabled={!identity.trim() || add.isPending} data-testid="buyer-add">{t("buyers.add")}</button>
          </div>
        )}
        <small style={{ color: "var(--muted)" }}>{t("buyers.identityHelp")}</small>
        {add.error && <Alert tone="danger">{(add.error as Error).message}</Alert>}
      </form>

      {list.isLoading && <Skeleton h={120} />}
      {list.error && <Alert tone="warn">{(list.error as Error).message}</Alert>}
      {list.data && list.data.assignments.length === 0 && <EmptyState title={t("buyers.empty")} body="" />}
      <div style={{ display: "grid", gap: 8 }}>
        {list.data?.assignments.map((a) => (
          <article key={a.id} className="card" data-testid="buyer-row" style={{ padding: "0.8rem 1rem", display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <strong dir="ltr" style={{ flex: "1 1 220px", overflowWrap: "anywhere" }}>{a.identity}</strong>
            <span dir="auto" style={{ flex: "1 1 200px", color: "var(--muted)" }}>{names.get(a.contract_id) ?? a.contract_id.slice(0, 12)}</span>
            <span className="chip">{t(`buyers.channels.${a.channel}`, { defaultValue: a.channel })}</span>
            {a.created_by && <small style={{ color: "var(--muted)" }}>{t("buyers.by", { name: a.created_by })}</small>}
            <button className="btn btn-ghost" disabled={remove.isPending} onClick={() => remove.mutate(a.id)} data-testid="buyer-remove">{t("buyers.remove")}</button>
          </article>
        ))}
      </div>
      {remove.error && <Alert tone="danger">{(remove.error as Error).message}</Alert>}
    </div>
  );
}
