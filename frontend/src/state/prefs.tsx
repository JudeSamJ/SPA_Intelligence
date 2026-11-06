import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import i18n from "../i18n";

export type Theme = "day" | "dusk";
export type Lang = "en" | "ar";
/** full = everything; lite = mobile/low-power (no smooth scroll, WebGL, video); reduced = fades only. */
export type Tier = "full" | "lite" | "reduced";

interface Prefs {
  theme: Theme;
  setTheme: (t: Theme) => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  dir: "ltr" | "rtl";
  reduce: boolean;
  setReduce: (r: boolean) => void;
  tier: Tier;
  arabicDigits: boolean;
  setArabicDigits: (v: boolean) => void;
}

const Ctx = createContext<Prefs | null>(null);

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage may be blocked: preference just won't persist */
  }
}

function detectLowPower(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { connection?: { saveData?: boolean }; deviceMemory?: number };
  return (
    window.matchMedia("(pointer: coarse)").matches ||
    window.innerWidth < 768 ||
    !!nav.connection?.saveData ||
    (nav.hardwareConcurrency ?? 8) <= 2
  );
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (read("spa.theme") === "day" ? "day" : "dusk"));
  const [lang, setLangState] = useState<Lang>(() => (read("spa.lang") === "ar" ? "ar" : "en"));
  const [arabicDigits, setDigitsState] = useState<boolean>(() => read("spa.digits") === "1");
  const [osReduce, setOsReduce] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [userReduce, setUserReduce] = useState<string | null>(() => read("spa.reduce"));
  const [lowPower, setLowPower] = useState<boolean>(detectLowPower);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setOsReduce(mq.matches);
    mq.addEventListener("change", onChange);
    const onResize = () => setLowPower(detectLowPower());
    window.addEventListener("resize", onResize);
    return () => {
      mq.removeEventListener("change", onChange);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const reduce = userReduce === null ? osReduce : userReduce === "1";
  const tier: Tier = reduce ? "reduced" : lowPower ? "lite" : "full";
  const dir: "ltr" | "rtl" = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    const el = document.documentElement;
    el.dataset.theme = theme;
    el.dataset.effects = tier;
    el.lang = lang;
    el.dir = dir;
    void i18n.changeLanguage(lang);
  }, [theme, tier, lang, dir]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    write("spa.theme", t);
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    write("spa.lang", l);
  }, []);
  const setReduce = useCallback((r: boolean) => {
    setUserReduce(r ? "1" : "0");
    write("spa.reduce", r ? "1" : "0");
  }, []);
  const setArabicDigits = useCallback((v: boolean) => {
    setDigitsState(v);
    write("spa.digits", v ? "1" : "0");
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, lang, setLang, dir, reduce, setReduce, tier, arabicDigits, setArabicDigits }),
    [theme, setTheme, lang, setLang, dir, reduce, setReduce, tier, arabicDigits, setArabicDigits],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePrefs(): Prefs {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePrefs must be used inside PrefsProvider");
  return v;
}
