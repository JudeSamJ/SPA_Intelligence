import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiX, type GapResult, type PaidRow } from "../api/trust";
import { EvidenceLink } from "../components/EvidenceLink";
import { UnreviewedBadge } from "../components/UnreviewedBadge";
import { Alert, ErrorState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { useMotion } from "../motion/mm";
import { gsap } from "../motion/registry";
import { useContractCtx } from "./ctx";

const SCENARIOS = [30, 90, 180, 365];

function Bars({ r }: { r: GapResult }) {
  const { t } = useTranslation();
  const fmt = useFmt();
  const ref = useRef<HTMLDivElement>(null);
  const c = r.contractual?.penalty ?? 0;
  const s = r.statutory?.amount ?? 0;
  const max = Math.max(c, s, 1);
  useMotion(ref, ({ tier }) => {
    if (tier === "reduced") return;
    gsap.fromTo("[data-bar]", { scaleX: 0 }, { scaleX: 1, transformOrigin: "left center", duration: 0.7, ease: "power3.out", stagger: 0.12, clearProps: "transform" });
  }, [c, s]);
  const rows = [
    { key: "contract", label: t("gap.contract"), v: c, color: "var(--info)" },
    { key: "statute", label: t("gap.statute"), v: s, color: "var(--gold)" },
  ];
  return (
    <div ref={ref} role="img" aria-label={t("gap.barsLabel")} style={{ display: "grid", gap: 14 }} data-testid="gap-bars">
      {rows.map((b) => (
        <div key={b.key} style={{ display: "grid", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
            <strong>
              {b.label} {b.key === "statute" && r.unreviewed && <UnreviewedBadge />}
            </strong>
            <span className="num" data-testid={`gap-${b.key}`}>
              <AnimatedNumber value={b.v} format={(n) => fmt.aed(n, 2)} />
            </span>
          </div>
          <div style={{ background: "var(--surface-2)", borderRadius: 8, height: 26, overflow: "hidden" }}>
            <div data-bar style={{ width: `${(b.v / max) * 100}%`, height: "100%", background: b.color, borderRadius: 8 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Gap() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, detail } = useContractCtx();
  const c = detail.contract;
  const [days, setDays] = useState(180);
  const [asOf, setAsOf] = useState<string>(c.handover_date.value ?? new Date().toISOString().slice(0, 10));
  const [mode, setMode] = useState<"plan" | "user">("plan");
  const [paid, setPaid] = useState<PaidRow[]>([{ date: c.payment_plan[0]?.due_date ?? asOf, amount: 0 }]);
  const dDays = useDeferredValue(days);
  const dAsOf = useDeferredValue(asOf);
  const dPaid = useDeferredValue(paid);
  const q = useQuery({
    queryKey: ["gap", id, dDays, dAsOf, mode === "user" ? dPaid : "plan"],
    queryFn: () =>
      apiX.gap(id, {
        delay_days: dDays,
        as_of_date: dAsOf,
        amounts_paid: mode === "user" ? dPaid.filter((p) => p.amount > 0 && p.date) : undefined,
      }),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const r = q.data;
  const th = { textAlign: "start" as const, padding: "0.5rem 0.7rem", fontSize: "0.85rem", color: "var(--muted)" };
  const td = { padding: "0.5rem 0.7rem", borderBlockStart: "1px solid var(--line)", verticalAlign: "top" as const };

  return (
    <div className="data-layer" style={{ display: "grid", gap: "1.1rem" }}>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 12 }}>
        <h2 className="display" style={{ margin: 0, fontSize: "1.3rem" }}>{t("gap.title")}</h2>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("gap.intro")}</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "end" }}>
          <label style={{ display: "grid", gap: 4 }}>
            {t("gap.delayDays")}
            <input type="number" min={0} max={3650} value={days} style={{ minHeight: 44, width: 120 }}
              onChange={(e) => setDays(Math.max(0, Math.min(3650, Number(e.target.value) || 0)))} data-testid="gap-days" />
          </label>
          <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {SCENARIOS.map((d) => (
              <button key={d} className="chip" aria-pressed={days === d} onClick={() => setDays(d)}>{t("gap.nDays", { n: d })}</button>
            ))}
          </span>
          <label style={{ display: "grid", gap: 4 }}>
            {t("gap.asOf")}
            <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ minHeight: 44 }} data-testid="gap-asof" />
          </label>
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", gap: 8 }}>
            <legend style={{ fontSize: "0.9rem", marginBlockEnd: 4 }}>{t("gap.paidSource")}</legend>
            <button className="chip" aria-pressed={mode === "plan"} onClick={() => setMode("plan")}>{t("gap.fromPlan")}</button>
            <button className="chip" aria-pressed={mode === "user"} onClick={() => setMode("user")}>{t("gap.enterPayments")}</button>
          </fieldset>
        </div>
        {mode === "user" && (
          <div style={{ display: "grid", gap: 6 }} data-testid="paid-editor">
            {paid.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input type="date" aria-label={t("gap.paymentDate")} value={p.date} style={{ minHeight: 44 }}
                  onChange={(e) => setPaid(paid.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} />
                <input type="number" min={0} aria-label={t("gap.paymentAmount")} value={p.amount || ""} placeholder="0" style={{ minHeight: 44, width: 160 }}
                  onChange={(e) => setPaid(paid.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) || 0 } : x)))} />
                <button className="chip" onClick={() => setPaid(paid.filter((_, j) => j !== i))} aria-label={t("gap.removePayment")}>×</button>
              </div>
            ))}
            <button className="chip" style={{ justifySelf: "start" }} onClick={() => setPaid([...paid, { date: asOf, amount: 0 }])}>+ {t("gap.addPayment")}</button>
          </div>
        )}
      </section>

      {q.isLoading && <Skeleton h={220} />}
      {q.error && <ErrorState title={t("errors.generic")} message={(q.error as Error).message} onRetry={() => void q.refetch()} />}

      {r && !r.can_compute && (
        <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }} data-testid="gap-cannot">
          <Alert tone="warn"><strong>{t("gap.cannotCompute")}</strong> {r.reason}</Alert>
          {(r.needs_legal_review || r.entry) && <UnreviewedBadge />}
          {r.entry && <p style={{ margin: 0, color: "var(--muted)" }}>{r.entry.statute}, {r.entry.section}</p>}
        </section>
      )}

      {r?.can_compute && r.statutory && (
        <>
          <section className="card" style={{ padding: "1rem", display: "grid", gap: 14 }} aria-labelledby="gap-res">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
              <h2 id="gap-res" className="display" style={{ margin: 0, fontSize: "1.25rem", flex: 1 }}>{t("gap.result")}</h2>
              {r.unreviewed && <UnreviewedBadge />}
              <span className="chip" title={r.entry?.description}>{r.entry?.statute}, {r.entry?.section}</span>
            </div>
            {r.statutory.rate_table.illustrative && <Alert tone="warn" ><span data-testid="illustrative-rates">{t("gap.illustrative")}</span></Alert>}
            <Bars r={r} />
            {r.shortfall != null && (
              <div style={{ display: "grid", gap: 4 }}>
                <span style={{ color: "var(--muted)" }}>{t("gap.shortfall")}</span>
                <strong className="display num" data-testid="gap-shortfall" style={{ fontSize: "clamp(1.8rem,5vw,2.8rem)", color: r.one_sided ? "var(--danger)" : "var(--ok)" }}>
                  <AnimatedNumber value={r.shortfall} format={(n) => fmt.aed(n, 2)} />
                </strong>
                <span>{r.one_sided ? t("gap.oneSided") : t("gap.notOneSided")}</span>
              </div>
            )}
            {r.contractual_reason && <Alert tone="warn">{r.contractual_reason}</Alert>}
            {r.findings && r.findings.length > 0 && (
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 8 }} data-testid="gap-findings">
                {r.findings.map((f) => (
                  <li key={f.code} className="card" style={{ padding: "0.7rem 0.9rem", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", borderInlineStart: `4px solid ${f.severity === "high" ? "var(--danger)" : f.severity === "medium" ? "var(--warn)" : "var(--info)"}` }}>
                    <strong>{t(`gap.severity.${f.severity}`)}</strong>
                    <span style={{ flex: 1, minWidth: 200 }}>{f.message}</span>
                    {f.evidence_fields.map((ef) => (
                      <EvidenceLink key={ef} field={ef} page={r.evidence?.[ef]?.page} quote={r.evidence?.[ef]?.quote} />
                    ))}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card" style={{ overflowX: "auto" }} aria-labelledby="gap-in">
            <h3 id="gap-in" className="display" style={{ margin: 0, padding: "0.8rem 1rem 0", fontSize: "1.1rem" }}>{t("gap.inputs")}</h3>
            <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }} data-testid="gap-inputs">
              <thead><tr><th style={th}>{t("gap.input")}</th><th style={th}>{t("terms.value")}</th><th style={th}>{t("gap.source")}</th><th style={th}>{t("evidence.title")}</th></tr></thead>
              <tbody>
                {r.inputs?.map((i) => (
                  <tr key={i.label}>
                    <th scope="row" style={{ ...td, textAlign: "start", fontWeight: 600 }}>{i.label}</th>
                    <td style={td} className="num" data-label={t("terms.value")} dir="auto">{typeof i.value === "number" ? fmt.flex(i.value) : String(i.value ?? "–")}</td>
                    <td style={{ ...td, color: "var(--muted)" }} data-label={t("gap.source")}>{i.source}</td>
                    <td style={td} data-label={t("evidence.title")}>
                      {i.field ? <EvidenceLink field={i.field} page={r.evidence?.[i.field]?.page} quote={r.evidence?.[i.field]?.quote} /> : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <details className="card" style={{ padding: "0.8rem 1rem" }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>{t("gap.breakdown")}</summary>
            <div style={{ overflowX: "auto" }}>
              <table className="rtable" style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
                <thead><tr><th style={th}>{t("gap.payment")}</th><th style={th}>{t("gap.paymentDate")}</th><th style={th}>{t("terms.amount")}</th><th style={th}>{t("gap.daysAccrued")}</th><th style={th}>{t("gap.interest")}</th></tr></thead>
                <tbody>
                  {r.statutory.payments.map((p, i) => (
                    <tr key={i} style={{ opacity: p.counted ? 1 : 0.55 }}>
                      <th scope="row" style={{ ...td, textAlign: "start" }}>{p.label}{!p.counted && p.note ? ` (${p.note})` : ""}</th>
                      <td style={td} className="num" data-label={t("gap.paymentDate")}>{fmt.date(p.date)}</td>
                      <td style={td} className="num" data-label={t("terms.amount")}>{fmt.aed(p.amount, 2)}</td>
                      <td style={td} className="num" data-label={t("gap.daysAccrued")}>{fmt.num(p.days)}</td>
                      <td style={td} className="num" data-label={t("gap.interest")}>{fmt.aed(p.interest, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ color: "var(--muted)" }}>
              {t("gap.rateTable")}: {r.statutory.rate_table.name} · {r.statutory.rate_table.rows.map((x) => `${fmt.date(x.effective_from)}: ${fmt.flex(x.rate_pct)}%`).join(" · ")} · {t("gap.spread")}: {fmt.flex(r.statutory.spread_pct)}%
            </p>
          </details>
        </>
      )}
    </div>
  );
}
