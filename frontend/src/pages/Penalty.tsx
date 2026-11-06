import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, type PenaltyResponse } from "../api/client";
import { usePenalty } from "../api/hooks";
import { PenaltyDial } from "../components/PenaltyDial";
import { Alert, EmptyState, Skeleton } from "../components/ui";
import { useFmt } from "../i18n/format";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { useContractCtx } from "./ctx";

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => {
    const id = setTimeout(() => setD(v), ms);
    return () => clearTimeout(id);
  }, [v, ms]);
  return d;
}

export default function Penalty() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, openPdf } = useContractCtx();
  const base = usePenalty(id); // default scenarios from rules/uae.yaml
  const [days, setDays] = useState<number | null>(null);
  const initial =
    base.data?.default_scenarios[Math.floor((base.data.default_scenarios.length - 1) / 2) + 1] ??
    base.data?.default_scenarios[0];
  const current = days ?? initial ?? 0;
  const debounced = useDebounced(current, 180);
  const one = usePenalty(id, base.data ? [debounced] : undefined);

  if (base.error) {
    const e = base.error as ApiError;
    return <EmptyState title={t("penalty.unavailable")} body={e.message} />;
  }
  if (!base.data) return <Skeleton h={360} />;
  const d: PenaltyResponse = base.data;
  const max = Math.max(...d.default_scenarios);
  const row = one.data?.rows[0];
  const terms = d.terms;
  const termRows: Array<[string, string, number | null | undefined, string | null | undefined]> = [
    [
      t("penalty.rate"),
      terms.basis.value === "fixed_per_sqft_per_year"
        ? t("terms.rateFixed", { value: fmt.aed(terms.rate.value ?? 0, 2) })
        : t("terms.ratePercent", { value: `${fmt.flex(terms.rate.value ?? 0)}%` }),
      terms.rate.source_page,
      terms.rate.source_quote,
    ],
    [
      t("penalty.basis"),
      t(`terms.basis.${terms.basis.value ?? "other"}`),
      terms.basis.source_page,
      terms.basis.source_quote,
    ],
    [
      t("terms.fields.grace_period_days"),
      t("terms.daysValue", { value: fmt.num(terms.grace_days.value ?? 0) }),
      terms.grace_days.source_page,
      terms.grace_days.source_quote,
    ],
    [
      t("penalty.cap"),
      terms.cap_pct.value != null
        ? t("terms.capValue", { value: `${fmt.flex(terms.cap_pct.value)}%` })
        : t("penalty.noCap"),
      terms.cap_pct.source_page,
      terms.cap_pct.source_quote,
    ],
    [
      t("penalty.price"),
      terms.price.value != null ? fmt.aed(terms.price.value, 0) : "–",
      terms.price.source_page,
      terms.price.source_quote,
    ],
    [
      t("penalty.area"),
      terms.area_sqft.value != null ? t("terms.sqft", { value: fmt.num(terms.area_sqft.value, 2) }) : "–",
      terms.area_sqft.source_page,
      terms.area_sqft.source_quote,
    ],
  ];
  const th = {
    textAlign: "start" as const,
    padding: "0.55rem 0.8rem",
    fontSize: "0.85rem",
    color: "var(--muted)",
  };
  const td = { padding: "0.6rem 0.8rem", borderBlockStart: "1px solid var(--line)" };
  return (
    <div className="data-layer" style={{ display: "grid", gap: "1.2rem" }}>
      <p style={{ margin: 0, color: "var(--muted)", maxWidth: "70ch" }}>{t("penalty.intro")}</p>
      <section
        className="card"
        style={{
          padding: "1.2rem",
          display: "grid",
          gap: "1.4rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          alignItems: "center",
        }}
      >
        <PenaltyDial value={current} max={max} presets={d.default_scenarios} onChange={setDays} />
        <div style={{ display: "grid", gap: 14 }} aria-live="polite">
          <div>
            <div style={{ color: "var(--muted)" }}>{t("penalty.owed")}</div>
            <div
              data-testid="penalty-amount"
              style={{ fontSize: "clamp(1.8rem,4vw,2.8rem)", fontWeight: 700 }}
              className="display"
            >
              {row ? (
                <AnimatedNumber value={row.penalty} format={(n) => fmt.aed(n, 2)} />
              ) : (
                <Skeleton h={44} w={220} />
              )}
            </div>
          </div>
          {row && (
            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                gap: 12,
                margin: 0,
              }}
            >
              <div>
                <dt style={{ color: "var(--muted)" }}>{t("penalty.chargeable")}</dt>
                <dd style={{ margin: 0, fontWeight: 700 }} className="num" data-testid="chargeable">
                  {fmt.num(row.chargeable_days)}
                </dd>
              </div>
              <div>
                <dt style={{ color: "var(--muted)" }}>{t("penalty.pctPrice")}</dt>
                <dd style={{ margin: 0, fontWeight: 700 }} className="num">
                  {row.pct_of_price != null ? fmt.pct(row.pct_of_price, 3) : "–"}
                </dd>
              </div>
              <div>
                <dt style={{ color: "var(--muted)" }}>{t("penalty.cap")}</dt>
                <dd style={{ margin: 0, fontWeight: 700 }} className="num">
                  {row.cap_amount != null ? fmt.aed(row.cap_amount, 0) : t("penalty.noCap")}
                </dd>
              </div>
            </dl>
          )}
          {row?.cap_reached && <Alert tone="warn">{t("penalty.capReached")}</Alert>}
        </div>
      </section>

      <section className="card" style={{ overflowX: "auto" }}>
        <h2 className="display" style={{ margin: 0, padding: "0.8rem", fontSize: "1.25rem" }}>
          {t("penalty.scenarios")}
        </h2>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
          <thead>
            <tr>
              {["delay", "grace", "chargeable", "amount", "capAmount"].map((h) => (
                <th key={h} scope="col" style={th}>
                  {t(h === "chargeable" ? "penalty.chargeable" : `penalty.${h}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r) => (
              <tr
                key={r.delay_days}
                data-testid="scenario-row"
                style={{ background: r.delay_days === current ? "var(--surface-2)" : undefined }}
              >
                <td style={td} className="num">
                  {fmt.num(r.delay_days)} {t("penalty.daysUnit")}
                </td>
                <td style={td} className="num">
                  {fmt.num(r.grace_days)}
                </td>
                <td style={td} className="num">
                  {fmt.num(r.chargeable_days)}
                </td>
                <td
                  style={{ ...td, fontWeight: 700 }}
                  className="num"
                  data-testid={`scenario-${r.delay_days}`}
                >
                  {fmt.aed(r.penalty, 2)}
                </td>
                <td style={td} className="num">
                  {r.cap_amount != null ? fmt.aed(r.cap_amount, 0) : t("penalty.noCap")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card" style={{ overflowX: "auto" }}>
        <h2 className="display" style={{ margin: 0, padding: "0.8rem", fontSize: "1.25rem" }}>
          {t("penalty.terms")}
        </h2>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
          <tbody>
            {termRows.map(([label, value, page, quote]) => (
              <tr key={label}>
                <th scope="row" style={{ ...td, textAlign: "start", width: "28%" }}>
                  {label}
                </th>
                <td style={{ ...td, fontWeight: 600 }} className="num" dir="auto">
                  {value}
                </td>
                <td style={{ ...td, color: "var(--muted)" }} dir="auto">
                  <span title={quote ?? ""}>{quote ?? ""}</span>
                </td>
                <td style={td}>
                  {page ? (
                    <button
                      className="chip num"
                      onClick={() => openPdf(page)}
                      aria-label={t("terms.openAtPage", { page })}
                    >
                      {fmt.num(page)}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
