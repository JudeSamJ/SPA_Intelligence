import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContractData } from "../api/client";
import { Alert, WarningCard } from "../components/ui";
import { useFmt } from "../i18n/format";
import { useMotion } from "../motion/mm";
import { Flip, gsap } from "../motion/registry";
import { ScrambleValue } from "../motion/ScrambleValue";
import { usePrefs } from "../state/prefs";
import { useContractCtx } from "./ctx";

type FieldKey =
  | "buyer"
  | "unit_id"
  | "price"
  | "area_sqft"
  | "handover_date"
  | "grace_period_days"
  | "delay_rate"
  | "delay_basis"
  | "delay_cap"
  | "cancellation_clause";
const FIELDS: FieldKey[] = [
  "buyer",
  "unit_id",
  "price",
  "area_sqft",
  "handover_date",
  "grace_period_days",
  "delay_rate",
  "delay_basis",
  "delay_cap",
  "cancellation_clause",
];

export default function Terms() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { tier } = usePrefs();
  const { detail, openPdf } = useContractCtx();
  const c = detail.contract;
  const warnings = c.warnings ?? [];
  const [sort, setSort] = useState<"field" | "page">("field");
  const flip = useRef<Flip.FlipState | null>(null);
  const root = useRef<HTMLDivElement>(null);

  const display = (k: FieldKey, cc: ContractData): { text: string; missing: boolean } => {
    const item = cc[k];
    const v = item.value as unknown;
    if (k === "cancellation_clause")
      return v != null
        ? { text: t("terms.present"), missing: false }
        : { text: t("terms.notFound"), missing: true };
    if (k === "delay_cap") {
      if (v != null)
        return { text: t("terms.capValue", { value: `${fmt.flex(v as number)}%` }), missing: false };
      return item.source_quote
        ? { text: t("terms.noCap"), missing: false }
        : { text: t("common.notStated"), missing: true };
    }
    if (v == null) return { text: t("common.notStated"), missing: true };
    switch (k) {
      case "price":
        return { text: fmt.aed(v as number, 0), missing: false };
      case "area_sqft":
        return { text: t("terms.sqft", { value: fmt.num(v as number, 2) }), missing: false };
      case "handover_date":
        return { text: fmt.date(v as string), missing: false };
      case "grace_period_days":
        return { text: t("terms.daysValue", { value: fmt.num(v as number) }), missing: false };
      case "delay_basis":
        return { text: t(`terms.basis.${String(v)}`), missing: false };
      case "delay_rate": {
        const basis = cc.delay_basis.value;
        return {
          text:
            basis === "fixed_per_sqft_per_year"
              ? t("terms.rateFixed", { value: fmt.aed(v as number, 2) })
              : basis === "percent_per_annum"
                ? t("terms.ratePercent", { value: `${fmt.flex(v as number)}%` })
                : fmt.flex(v as number),
          missing: false,
        };
      }
      default:
        return { text: String(v), missing: false };
    }
  };

  const rows = useMemo(() => {
    const base = FIELDS.map((k, i) => ({ k, i, item: c[k] }));
    return sort === "page"
      ? [...base].sort((a, b) => (a.item.source_page ?? 999) - (b.item.source_page ?? 999) || a.i - b.i)
      : base;
  }, [c, sort]);

  const toggleSort = () => {
    flip.current = Flip.getState("[data-row]");
    setSort((s) => (s === "field" ? "page" : "field"));
  };
  useLayoutEffect(() => {
    if (flip.current && tier !== "reduced")
      Flip.from(flip.current, { duration: 0.55, ease: "power3.inOut", targets: "[data-row]" });
    flip.current = null;
  }, [sort, tier]);

  useMotion(
    root,
    ({ tier: tr }) => {
      if (tr === "reduced") return;
      gsap.from(gsap.utils.toArray("[data-row]", root.current), {
        y: 14,
        opacity: 0,
        duration: 0.5,
        stagger: 0.04,
        clearProps: "transform,opacity",
      });
    },
    [detail.id],
  );

  const sum = c.payment_plan_percent_sum;
  const bad = sum != null && Math.abs(sum - 100) > 0.01;
  const th = {
    textAlign: "start" as const,
    padding: "0.6rem 0.8rem",
    fontSize: "0.85rem",
    color: "var(--muted)",
    fontWeight: 700,
  };
  const td = {
    padding: "0.65rem 0.8rem",
    verticalAlign: "top" as const,
    borderBlockStart: "1px solid var(--line)",
  };

  return (
    <div ref={root} className="data-layer" style={{ display: "grid", gap: "1.2rem" }}>
      <section aria-label={t("terms.warnings")} style={{ display: "grid", gap: 8 }}>
        {warnings.length ? (
          warnings.map((w) => <WarningCard key={w}>{w}</WarningCard>)
        ) : (
          <Alert tone="ok">{t("terms.noWarnings")}</Alert>
        )}
      </section>

      <section className="card" style={{ overflowX: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0.8rem 0.8rem 0" }}>
          <h2 className="display" style={{ margin: 0, fontSize: "1.3rem", flex: 1 }}>
            {t("terms.title")}
          </h2>
          <button className="chip" onClick={toggleSort} aria-pressed={sort === "page"}>
            {sort === "page" ? t("terms.sortByField") : t("terms.sortByPage")}
          </button>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
          <thead>
            <tr>
              <th scope="col" style={th}>
                {t("terms.field")}
              </th>
              <th scope="col" style={th}>
                {t("terms.value")}
              </th>
              <th scope="col" style={th}>
                {t("terms.page")}
              </th>
              <th scope="col" style={th}>
                {t("terms.quote")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ k, item }) => {
              const d = display(k, c);
              return (
                <tr
                  key={k}
                  data-row
                  data-testid={`row-${k}`}
                  style={{ background: d.missing ? "var(--warn-bg)" : undefined }}
                >
                  <th scope="row" style={{ ...td, textAlign: "start", fontWeight: 600 }}>
                    {t(`terms.fields.${k}`)}
                  </th>
                  <td style={td} data-testid={`value-${k}`} dir="auto">
                    <ScrambleValue text={d.text} />
                  </td>
                  <td style={td} className="num">
                    {item.source_page ? (
                      <button
                        className="chip"
                        onClick={() => openPdf(item.source_page!)}
                        aria-label={t("terms.openAtPage", { page: item.source_page })}
                      >
                        {fmt.num(item.source_page)}
                      </button>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td style={{ ...td, color: "var(--muted)" }} dir="auto">
                    <span
                      style={{
                        display: "-webkit-box",
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                      title={item.source_quote ?? ""}
                    >
                      {item.source_quote ?? "–"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="card" style={{ overflowX: "auto" }} aria-labelledby="plan-h">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14, padding: "0.8rem" }}>
          <h2 id="plan-h" className="display" style={{ margin: 0, fontSize: "1.3rem", flex: 1 }}>
            {t("terms.plan")}
          </h2>
          <span>
            {t("terms.milestones")}: <strong className="num">{fmt.num(detail.plan.length)}</strong>
          </span>
          <span
            data-testid="plan-total"
            style={{
              padding: "0.25rem 0.8rem",
              borderRadius: 999,
              fontWeight: 700,
              background: bad ? "var(--danger-bg)" : "var(--ok-bg)",
              color: bad ? "var(--danger)" : "var(--ok)",
              border: `1px solid ${bad ? "var(--danger)" : "var(--ok)"}`,
            }}
          >
            {t("terms.planTotal")}:{" "}
            <span className="num">{sum != null ? fmt.pct(sum, sum % 1 ? 2 : 0) : "–"}</span>
          </span>
        </div>
        {bad && sum != null && (
          <div style={{ padding: "0 0.8rem 0.8rem" }}>
            <Alert tone="danger">{t("terms.notTotal100", { total: fmt.pct(sum, 2) })}</Alert>
          </div>
        )}
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
          <thead>
            <tr>
              {["milestone", "percent", "amount", "due", "trigger", "type", "page"].map((h) => (
                <th key={h} scope="col" style={th}>
                  {t(h === "page" ? "terms.page" : `terms.${h}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {detail.plan.map((p, i) => (
              <tr
                key={i}
                data-row
                data-testid="plan-row"
                style={{ background: bad ? "var(--warn-bg)" : undefined }}
              >
                <th scope="row" style={{ ...td, textAlign: "start", fontWeight: 600 }} dir="auto">
                  {p.milestone}
                </th>
                <td style={td} className="num">
                  {fmt.pct(p.percent, p.percent % 1 ? 2 : 0)}
                </td>
                <td style={td} className="num">
                  {fmt.aed(p.amount, 2)}
                </td>
                <td style={td} className="num">
                  {p.due_date ? fmt.date(p.due_date) : "–"}
                </td>
                <td style={{ ...td, color: "var(--muted)" }} dir="auto">
                  {p.trigger ?? "–"}
                </td>
                <td style={td}>{t(`terms.types.${p.type}`)}</td>
                <td style={td}>
                  <button
                    className="chip num"
                    title={p.source_quote}
                    aria-label={t("terms.openAtPage", { page: p.source_page })}
                    onClick={() => openPdf(p.source_page)}
                  >
                    {fmt.num(p.source_page)}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
