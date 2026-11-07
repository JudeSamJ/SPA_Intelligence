import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Obligation } from "../api/trust";
import { usePrefs } from "../state/prefs";

const COLOR: Record<string, string> = { high: "var(--danger)", medium: "var(--warn)", low: "var(--info)", none: "var(--muted)" };

/** Month grid for one contract's obligations. */
export function ObligationCalendar({ rows, asOf }: { rows: Obligation[]; asOf: string }) {
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const first = rows.find((r) => r.due_date >= asOf)?.due_date ?? rows[0]?.due_date ?? asOf;
  const [ym, setYm] = useState(first.slice(0, 7));
  const y = Number(ym.slice(0, 4));
  const m = Number(ym.slice(5, 7));
  const start = new Date(Date.UTC(y, m - 1, 1));
  const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const lead = (start.getUTCDay() + 6) % 7;     // Monday first
  const shift = (n: number) => {
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setYm(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  };
  const by = new Map<string, Obligation[]>();
  rows.forEach((r) => by.set(r.due_date, [...(by.get(r.due_date) ?? []), r]));
  const title = new Intl.DateTimeFormat(lang === "ar" ? "ar-AE-u-nu-latn" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(start);
  const cells = [...Array(lead).fill(null), ...Array.from({ length: dim }, (_, i) => i + 1)];
  return (
    <div data-testid="obl-calendar" className="card" style={{ padding: "0.8rem", display: "grid", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button className="chip" onClick={() => shift(-1)} aria-label={t("obl.prevMonth")}>‹</button>
        <strong style={{ flex: 1, textAlign: "center" }}>{title}</strong>
        <button className="chip" onClick={() => shift(1)} aria-label={t("obl.nextMonth")}>›</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: 4 }}>
        {cells.map((d, i) => {
          if (d === null) return <div key={`b${i}`} />;
          const iso = `${ym}-${String(d).padStart(2, "0")}`;
          const items = by.get(iso) ?? [];
          return (
            <div key={iso} style={{ minHeight: 52, border: "1px solid var(--line)", borderRadius: 6, padding: 3, fontSize: "0.78rem", background: iso === asOf ? "var(--accent-fill-soft, var(--surface-2))" : undefined }}>
              <span className="num">{d}</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
                {items.map((o) => (
                  <span key={o.id} title={o.label} data-testid="cal-dot" style={{ width: 10, height: 10, borderRadius: 99, background: COLOR[o.severity] }} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
