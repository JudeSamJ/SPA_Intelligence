import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { usePrefs } from "../state/prefs";

const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const toArabicIndic = (s: string) => s.replace(/[0-9]/g, (d) => AR_DIGITS[Number(d)] ?? d);

/** Locale-aware formatters. Western digits by default; Arabic-Indic digits only if the user opts in (AR mode). */
export function makeFormatters(lang: "en" | "ar", arabicDigits: boolean, aedLabel: string) {
  const useArab = lang === "ar" && arabicDigits;
  const locale = lang === "ar" ? `ar-AE-u-nu-${useArab ? "arab" : "latn"}` : "en-GB";
  const num = (n: number, decimals = 0) =>
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(n);
  const aed = (n: number, decimals = 2) =>
    lang === "ar" ? `${num(n, decimals)} ${aedLabel}` : `${aedLabel} ${num(n, decimals)}`;
  /** 490000 -> "490K" (axis labels on phones) */
  const compact = (n: number) =>
    new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(n);
  const pct = (n: number, decimals = 0) => `${num(n, decimals)}%`;
  /** up to 2 decimals, trailing zeros trimmed (20 -> "20", 12.5 -> "12.5") */
  const flex = (n: number) =>
    new Intl.NumberFormat(locale, { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(n);
  /** DD MMM YYYY */
  const date = (iso: string | null | undefined) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    if (!y || !m || !d) return iso;
    const month = new Intl.DateTimeFormat(lang === "ar" ? "ar-AE-u-nu-latn" : "en-GB", {
      month: "short",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(y, m - 1, d)));
    const out = `${String(d).padStart(2, "0")} ${month} ${y}`;
    return useArab ? toArabicIndic(out) : out;
  };
  return { num, aed, pct, date, flex, compact };
}

export function useFmt() {
  const { lang, arabicDigits } = usePrefs();
  const { t } = useTranslation();
  const aedLabel = t("common.aed");
  const f = useMemo(() => makeFormatters(lang, arabicDigits, aedLabel), [lang, arabicDigits, aedLabel]);
  const period = useCallback(
    (key: string) => {
      // "2026-Q2" / "2026-05" -> localised label
      const q = /^(\d{4})-Q(\d)$/.exec(key);
      if (q) return f.num(Number(q[1])).replace(/[,٬]/g, "") + ` Q${f.num(Number(q[2]))}`;
      return key;
    },
    [f],
  );
  return { ...f, period };
}
