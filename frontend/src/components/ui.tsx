import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { dustFall } from "../motion/effects";
import { useMotion } from "../motion/mm";
import { gsap, loadMorph } from "../motion/registry";
import { CIRCLE_D, MashrabiyaBand, MashrabiyaLoader, STAR_D } from "../scenes/Mashrabiya";
import { usePrefs } from "../state/prefs";

/** Mashrabiya loader: the star draws itself (DrawSVG) while the inner shape morphs circle <-> star (MorphSVG). */
export function Loader({ label, size = 96 }: { label: string; size?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useMotion(ref, ({ tier }) => {
    if (tier === "reduced") return;
    const q = gsap.utils.selector(ref.current!);
    gsap.fromTo(
      q(".loader-star"),
      { drawSVG: "0% 0%" },
      { drawSVG: "0% 100%", duration: 1.4, repeat: -1, yoyo: true, ease: "power1.inOut" },
    );
    gsap.to(q(".loader-sq"), {
      rotate: 90,
      transformOrigin: "50% 50%",
      duration: 3,
      repeat: -1,
      ease: "none",
    });
    let tw: gsap.core.Tween | undefined;
    void loadMorph().then(() => {
      tw = gsap.to(q(".loader-inner"), {
        morphSVG: { shape: STAR_D, shapeIndex: "auto" },
        duration: 1.2,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
      });
    });
    return () => void tw?.kill();
  });
  void CIRCLE_D;
  return (
    <div ref={ref} style={{ color: "var(--gold)", display: "grid", placeItems: "center" }}>
      <MashrabiyaLoader label={label} size={size} />
    </div>
  );
}

export function Skeleton({ h = 120, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" aria-hidden="true" style={{ height: h, width: w }} />;
}

/** Error state with falling dust (PhysicsPropsPlugin), never on data. */
export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();
  useEffect(() => {
    if (ref.current) void dustFall(ref.current, tier);
  }, [tier]);
  return (
    <div
      ref={ref}
      role="alert"
      className="card"
      style={{ position: "relative", overflow: "hidden", padding: "1.5rem", borderColor: "var(--danger)" }}
    >
      <h2 className="display" style={{ margin: 0, fontSize: "1.3rem", color: "var(--danger)" }}>
        {title}
      </h2>
      {message && <p style={{ color: "var(--muted)", margin: "0.5rem 0 0" }}>{message}</p>}
      {onRetry && (
        <button className="btn btn-ghost" style={{ marginBlockStart: 14 }} onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  children,
}: {
  title: string;
  body?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className="card"
      style={{
        padding: "2.2rem 1.5rem",
        textAlign: "center",
        display: "grid",
        justifyItems: "center",
        gap: 10,
      }}
    >
      <div style={{ color: "var(--accent)", width: "100%", maxWidth: 260 }}>
        <MashrabiyaBand height={22} opacity={0.7} />
      </div>
      <h2 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>
        {title}
      </h2>
      {body && <p style={{ color: "var(--muted)", margin: 0, maxWidth: "50ch" }}>{body}</p>}
      {children}
    </div>
  );
}

export function Alert({ tone, children }: { tone: "warn" | "danger" | "ok" | "info"; children: ReactNode }) {
  const map = {
    warn: ["var(--warn-bg)", "var(--gold-ink)"],
    danger: ["var(--danger-bg)", "var(--danger)"],
    ok: ["var(--ok-bg)", "var(--ok)"],
    info: ["var(--surface-2)", "var(--info)"],
  } as const;
  const [bg, fg] = map[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      style={{
        background: bg,
        color: "var(--fg)",
        borderInlineStart: `4px solid ${fg}`,
        padding: "0.7rem 1rem",
        borderRadius: 8,
      }}
    >
      {children}
    </div>
  );
}

/** Warning card: CustomWiggle on appear. */
export function WarningCard({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { tier } = usePrefs();
  useEffect(() => {
    if (tier === "reduced" || !ref.current) return;
    const tw = gsap.fromTo(
      ref.current,
      { rotation: 0 },
      {
        rotation: 1.2,
        duration: 0.9,
        ease: "alertWiggle",
        transformOrigin: "50% 50%",
        clearProps: "rotation",
      },
    );
    return () => void tw.kill();
  }, [tier]);
  return (
    <div
      ref={ref}
      role="alert"
      style={{
        background: "var(--danger-bg)",
        color: "var(--fg)",
        border: "1px solid var(--danger)",
        padding: "0.7rem 1rem",
        borderRadius: 10,
        display: "flex",
        gap: 10,
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--danger)" }}>
        ▲
      </span>
      <span>{children}</span>
    </div>
  );
}
