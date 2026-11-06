import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Magnetic } from "../motion/Magnetic";
import { EASE } from "../motion/ease";
import { useMotion } from "../motion/mm";
import { gsap, loadMorph, loadSmoother, Observer, ScrollTrigger } from "../motion/registry";
import { getScrollY, scrollToTarget, setSmoother } from "../motion/scroll";
import { splitReveal } from "../motion/split";
import { useGo } from "../motion/Transition";
import { Dhow, Falcon } from "../scenes/Silhouettes";
import { HeroBackdrop } from "../scenes/HeroBackdrop";
import { GoldTrail } from "../scenes/GoldTrail";
import { MashrabiyaBand, MashrabiyaLoader } from "../scenes/Mashrabiya";
import { Marquee } from "../scenes/Marquee";
import { Palm } from "../scenes/Palm";
import { Skyline, SKY_D } from "../scenes/Skyline";
import { usePrefs } from "../state/prefs";

const FEATURES = ["extraction", "penalty", "cashflow", "assistant"] as const;
const ROADMAP = ["docint", "cross", "bilingual", "rulebook", "whatsapp", "evalset"] as const;
const LIGHT = "#f3ead3";

export default function Landing() {
  const { t } = useTranslation();
  const { tier, theme } = usePrefs();
  const go = useGo();
  const root = useRef<HTMLDivElement>(null);
  const intro = useRef<gsap.core.Timeline | null>(null);
  const [ready, setReady] = useState(tier !== "full");
  const [introDone, setIntroDone] = useState(false);
  const firstTheme = useRef(true);

  // ScrollSmoother: landing only, full tier only (desktop, effects on). Must exist before ScrollTriggers are created.
  useEffect(() => {
    if (tier !== "full") {
      setReady(true);
      return;
    }
    setReady(false);
    let dead = false;
    let sm: { kill: () => void } | null = null;
    void loadSmoother().then(({ ScrollSmoother }) => {
      if (dead) return;
      sm = ScrollSmoother.create({
        wrapper: "#smooth-wrapper",
        content: "#smooth-content",
        smooth: 1.1,
        effects: true,
        smoothTouch: false,
      });
      setSmoother(sm);
      setReady(true);
    });
    return () => {
      dead = true;
      setSmoother(null);
      sm?.kill();
      setReady(false);
    };
  }, [tier]);

  // --- hero: split headline, scramble tagline, dhow on a motion path, Observer gate -------------------------
  useMotion(
    root,
    ({ tier: tr, rtl, dirSign }) => {
      if (!ready) return;
      const cleanups: Array<() => void> = [];
      const title = root.current!.querySelector<HTMLElement>("[data-hero-title]")!;
      const tag = root.current!.querySelector<HTMLElement>("[data-hero-tag]")!;
      if (tr === "reduced") return;
      const tl = gsap.timeline({ onComplete: () => setIntroDone(true) });
      intro.current = tl;
      cleanups.push(splitReveal(title, { rtl, delay: 0.2 }));
      tl.from("[data-hero-eyebrow]", { y: 20, opacity: 0, duration: 1.4, ease: EASE.slow }, 0.1)
        .fromTo(
          tag,
          { scrambleText: { text: "", chars: "upperCase", speed: 0.6 } },
          {
            scrambleText: { text: tag.textContent ?? "", chars: "·✦·", revealDelay: 0.4, speed: 0.5 },
            duration: 1.6,
            ease: "none",
          },
          1.0,
        )
        .from(
          "[data-hero-cta] > *",
          { y: 40, opacity: 0, stagger: 0.12, duration: 1.1, ease: EASE.bounce },
          1.4,
        )
        .from("[data-hero-skip]", { opacity: 0, duration: 0.4 }, 0.5);
      // dhow follows a wavy path along the horizon, mirrored in RTL
      if (tr === "full") {
        gsap.to("[data-dhow]", {
          duration: 70,
          repeat: -1,
          ease: "none",
          motionPath: {
            path: "#hero-wave",
            align: "#hero-wave",
            alignOrigin: [0.5, 0.9],
            autoRotate: false,
            start: rtl ? 1 : 0,
            end: rtl ? 0 : 1,
          },
        });
        gsap.to("[data-falcon]", {
          x: dirSign * 120,
          y: -26,
          duration: 9,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
        });
      }
      // Observer: the first deliberate wheel/swipe down from the hero glides to the next scene
      const gate = { busy: false };
      const obs = Observer.create({
        target: window,
        type: "wheel,touch",
        tolerance: 24,
        preventDefault: false,
        onDown: () => {
          if (gate.busy || getScrollY() > 40) return;
          gate.busy = true;
          scrollToTarget("#palm", 0);
          gsap.delayedCall(1.4, () => void (gate.busy = false));
        },
      });
      cleanups.push(() => obs.kill());
      return () => cleanups.forEach((c) => c());
    },
    [ready],
  );

  // --- palm scene: DrawSVG + plane on the crescent path (pinned + scrubbed) -------------------------------
  useMotion(
    root,
    ({ tier: tr, rtl, desktop }) => {
      if (!ready || tr === "reduced") return;
      const q = gsap.utils.selector(root.current!);
      gsap.set(q("#palm .draw"), { drawSVG: "0%" });
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: "#palm",
          start: "top top",
          end: desktop && tr === "full" ? "+=130%" : "+=60%",
          pin: desktop && tr === "full",
          scrub: tr === "full" ? 1 : true,
          anticipatePin: 1,
        },
      });
      tl.to(q("#palm .draw"), { drawSVG: "100%", stagger: 0.05, duration: 1 })
        .from(
          q("#palm .palm-copy > *"),
          { y: 30, opacity: 0, stagger: 0.2, duration: 0.6, ease: "power3.out" },
          0.2,
        )
        .fromTo("#plane", { opacity: 0 }, { opacity: 1, duration: 0.1 }, 0.5)
        .to(
          "#plane",
          {
            motionPath: {
              path: "#palm-crescent",
              align: "#palm-crescent",
              alignOrigin: [0.5, 0.5],
              autoRotate: true,
              start: rtl ? 1 : 0,
              end: rtl ? 0 : 1,
            },
            duration: 1.4,
          },
          0.5,
        )
        .to("#palm-marker", { attr: { r: 9 }, duration: 0.3, ease: "back.out(2)" }, 1.4);
      return () => void tl.scrollTrigger?.kill();
    },
    [ready],
  );

  // --- skyline: pinned, floors light up as features scroll by; sky shifts golden -> night; snap to labels ---
  useMotion(
    root,
    ({ tier: tr, desktop }) => {
      if (!ready || tr === "reduced") return;
      const q = gsap.utils.selector(root.current!);
      const pin = desktop && tr === "full";
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: "#skyline",
          start: "top top",
          end: pin ? "+=320%" : "+=140%",
          pin,
          scrub: tr === "full" ? 1 : true,
          anticipatePin: 1,
          snap: pin
            ? { snapTo: "labels", duration: { min: 0.2, max: 0.6 }, delay: 0.1, ease: "power1.inOut" }
            : undefined,
        },
      });
      tl.fromTo(
        "#sky-scene",
        { "--sky-top": "#2d2a5a", "--sky-bot": "#f0a35a" },
        { "--sky-top": "#0b1b2b", "--sky-bot": "#3b2250", duration: 4 },
        0,
      ).fromTo("#sky-progress", { scaleY: 0 }, { scaleY: 1, duration: 4 }, 0);
      FEATURES.forEach((_, i) => {
        tl.addLabel(`f${i}`, i)
          // highlight by scale + border, never by fading the text (keeps contrast >= 4.5:1 at every scroll position)
          .to(q(`[data-feature]`), { scale: 0.97, borderColor: "rgba(243,234,211,.25)", duration: 0.2 }, i)
          .to(q(`[data-feature="${i}"]`), { scale: 1.02, borderColor: "#d4a24c", duration: 0.3 }, i)
          .to(
            q(`#burj [data-win][data-band="${i}"], #burj [data-band="${i}"] ~ [data-win]`),
            { opacity: 0.95, stagger: { each: 0.04, from: "random" }, duration: 0.6 },
            i,
          )
          .to(
            q("[data-win]:not(#burj [data-win])").slice(i * 20, i * 20 + 40),
            { opacity: 0.8, stagger: 0.02, duration: 0.5 },
            i + 0.2,
          );
      });
      tl.to("#burj-beacon", { opacity: 1, duration: 0.3 }, 3.6).addLabel("end", 4);
      return () => void tl.scrollTrigger?.kill();
    },
    [ready],
  );

  // --- horizontal-scroll roadmap gallery (pinned) ---------------------------------------------------------
  useMotion(
    root,
    ({ tier: tr, rtl, desktop }) => {
      if (!ready || tr === "reduced") return;
      const track = root.current!.querySelector<HTMLElement>("#road-track")!;
      if (!(desktop && tr === "full")) return;
      const dist = () => Math.max(0, track.scrollWidth - window.innerWidth + 80);
      const tw = gsap.to(track, {
        x: () => (rtl ? dist() : -dist()),
        ease: "none",
        scrollTrigger: {
          trigger: "#roadmap",
          start: "top top",
          end: () => `+=${dist()}`,
          pin: true,
          scrub: 1,
          invalidateOnRefresh: true,
          anticipatePin: 1,
        },
      });
      return () => void tw.scrollTrigger?.kill();
    },
    [ready],
  );

  // --- batch reveals + CTA ---------------------------------------------------------------------------------
  useMotion(
    root,
    ({ tier: tr }) => {
      if (!ready || tr === "reduced") return;
      const items = gsap.utils.toArray<HTMLElement>(".reveal", root.current);
      gsap.set(items, { opacity: 0, y: 40 });
      const batch = ScrollTrigger.batch(items, {
        start: "top 90%",
        once: true,
        onEnter: (els) =>
          void gsap.to(els, { opacity: 1, y: 0, stagger: 0.12, duration: 0.8, overwrite: true }),
      });
      return () => batch.forEach((s) => s.kill());
    },
    [ready],
  );

  // --- sun/moon: skyline silhouette morphs between day and night variants --------------------------------
  useEffect(() => {
    if (firstTheme.current) {
      firstTheme.current = false;
      return;
    }
    if (tier === "reduced") return;
    let tw: gsap.core.Tween | undefined;
    void loadMorph().then(() => {
      tw = gsap.to("#skyline-back", {
        duration: 1.2,
        ease: "power3.inOut",
        morphSVG: { shape: SKY_D[theme], shapeIndex: "auto" },
      });
    });
    return () => void tw?.kill();
  }, [theme, tier]);

  const skip = () => {
    intro.current?.progress(1);
    setIntroDone(true);
  };

  return (
    <div id="smooth-wrapper" ref={root} style={{ color: LIGHT }}>
      <GoldTrail />
      <div id="smooth-content">
        {/* ---------------- HERO ---------------- */}
        <section
          id="hero"
          aria-labelledby="hero-title"
          style={{
            position: "relative",
            minHeight: "100svh",
            display: "grid",
            placeItems: "center",
            overflow: "hidden",
          }}
        >
          <HeroBackdrop />
          <svg
            aria-hidden="true"
            viewBox="0 0 1600 200"
            preserveAspectRatio="none"
            style={{
              position: "absolute",
              insetInline: 0,
              bottom: "26%",
              width: "100%",
              height: 90,
              pointerEvents: "none",
              direction: "ltr",
            }}
          >
            <path
              id="hero-wave"
              d="M-100 120 Q 200 90 500 120 T 1100 120 T 1700 120"
              fill="none"
              stroke="rgba(255,226,160,.25)"
              strokeWidth="2"
            />
          </svg>
          <div
            data-dhow
            aria-hidden="true"
            style={{
              position: "absolute",
              top: 0,
              insetInlineStart: 0,
              width: 96,
              color: "#1a1222",
              pointerEvents: "none",
            }}
          >
            <Dhow />
          </div>
          <div
            data-falcon
            aria-hidden="true"
            style={{
              position: "absolute",
              top: "22%",
              insetInlineEnd: "16%",
              width: 70,
              color: "#f3ead3",
              opacity: 0.8,
            }}
          >
            <Falcon />
          </div>
          <div
            style={{ position: "relative", textAlign: "center", padding: "7rem 1.25rem 5rem", maxWidth: 980 }}
          >
            <p
              data-hero-eyebrow
              className="chip"
              style={{
                cursor: "default",
                color: LIGHT,
                borderColor: "rgba(243,234,211,.4)",
                background: "rgba(11,27,43,.5)",
              }}
            >
              {t("landing.eyebrow")}
            </p>
            <h1
              id="hero-title"
              data-hero-title
              data-glitch-title
              className="display"
              style={{
                fontSize: "clamp(2.4rem, 7vw, 5.6rem)",
                lineHeight: 1.05,
                margin: "1.2rem 0",
                fontWeight: 600,
              }}
            >
              {t("landing.title")}
            </h1>
            <p
              data-hero-tag
              className="display"
              style={{
                fontSize: "clamp(1.1rem, 2.4vw, 1.7rem)",
                color: "#f1cf8a",
                margin: "0 0 2rem",
                textShadow: "0 2px 14px rgba(11,27,43,.9)",
              }}
            >
              {t("landing.tagline")}
            </p>
            <div
              data-hero-cta
              style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}
            >
              <Magnetic>
                <button className="btn" onClick={() => go("/app")}>
                  {t("landing.ctaPrimary")}
                </button>
              </Magnetic>
              <Magnetic>
                <button
                  className="btn btn-ghost"
                  style={{ color: LIGHT, borderColor: "rgba(243,234,211,.55)" }}
                  onClick={() => scrollToTarget("#palm", 0)}
                >
                  {t("landing.ctaSecondary")}
                </button>
              </Magnetic>
            </div>
          </div>
          {!introDone && tier !== "reduced" && (
            <button
              data-hero-skip
              className="chip"
              onClick={skip}
              style={{
                position: "absolute",
                insetBlockEnd: "1.5rem",
                insetInlineEnd: "1.5rem",
                color: LIGHT,
                background: "rgba(11,27,43,.6)",
                borderColor: "rgba(243,234,211,.4)",
              }}
            >
              {t("common.skipIntro")}
            </button>
          )}
        </section>

        <div
          style={{ background: "#0b1b2b", padding: "1.4rem 0", borderBlock: "1px solid rgba(212,162,76,.3)" }}
        >
          <Marquee />
        </div>

        {/* ---------------- PALM ---------------- */}
        <section
          id="palm"
          aria-labelledby="palm-title"
          style={{
            position: "relative",
            minHeight: "100svh",
            background: "linear-gradient(180deg,#0b1b2b,#1b2347 60%,#2a2150)",
            display: "grid",
            alignItems: "center",
            overflow: "hidden",
          }}
        >
          <div className="grain" style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
          <div
            style={{
              position: "relative",
              display: "grid",
              gap: "2rem",
              gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
              alignItems: "center",
              maxWidth: 1200,
              margin: "0 auto",
              padding: "6rem 1.5rem 4rem",
            }}
          >
            <div className="palm-copy">
              <p className="num display" style={{ color: "var(--gold)", fontSize: "1.2rem", margin: 0 }}>
                {t("landing.palmStep")}
              </p>
              <h2
                id="palm-title"
                className="display"
                style={{ fontSize: "clamp(2rem,5vw,3.6rem)", margin: "0.4rem 0 1rem" }}
              >
                {t("landing.palmTitle")}
              </h2>
              <p style={{ fontSize: "1.15rem", lineHeight: 1.65, maxWidth: "34ch", color: "#d6dde3" }}>
                {t("landing.palmBody")}
              </p>
              <div style={{ color: "var(--gold)", marginBlockStart: 16 }}>
                <MashrabiyaBand height={26} opacity={0.6} />
              </div>
            </div>
            <div style={{ position: "relative", color: "var(--gold)", direction: "ltr" }}>
              <Palm />
              <svg
                id="plane"
                viewBox="0 0 24 24"
                width="30"
                height="30"
                aria-hidden="true"
                style={{ position: "absolute", top: 0, left: 0, opacity: 0, color: LIGHT }}
              >
                <path fill="currentColor" d="M2 11l20-8-6 18-4-7-7-3z" />
              </svg>
            </div>
          </div>
        </section>

        {/* ---------------- SKYLINE ---------------- */}
        <section
          id="skyline"
          aria-labelledby="sky-title"
          style={{ position: "relative", minHeight: "100svh", overflow: "hidden" }}
        >
          <div
            id="sky-scene"
            style={{
              position: "absolute",
              inset: 0,
              ["--sky-top" as string]: "#2d2a5a",
              ["--sky-bot" as string]: "#f0a35a",
              background: "linear-gradient(180deg, var(--sky-top), var(--sky-bot))",
            }}
          />
          <div className="grain" style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
          <div
            aria-hidden="true"
            style={{ position: "absolute", insetInline: 0, bottom: 0, height: "82%", color: "#150f24" }}
          >
            <Skyline initialTheme={theme} className="" />
          </div>
          <div
            style={{
              position: "absolute",
              insetInline: 0,
              top: 0,
              bottom: 0,
              background:
                "linear-gradient(180deg, rgba(11,27,43,.7), rgba(11,27,43,.25) 55%, rgba(11,27,43,.6))",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "relative",
              maxWidth: 1200,
              margin: "0 auto",
              padding: "6.5rem 1.5rem 3rem",
              display: "grid",
              gap: "1.2rem",
              alignContent: "start",
              minHeight: "100svh",
            }}
          >
            <h2
              id="sky-title"
              className="display"
              style={{ fontSize: "clamp(1.8rem,4.4vw,3.2rem)", margin: 0, maxWidth: "20ch" }}
            >
              {t("landing.skyTitle")}
            </h2>
            <ol
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "grid",
                gap: "0.8rem",
                maxWidth: 460,
              }}
            >
              {FEATURES.map((f, i) => (
                <li
                  key={f}
                  data-feature={i}
                  className="glass"
                  style={{
                    padding: "0.9rem 1.1rem",
                    background: "rgba(11,27,43,.82)",
                    borderColor: i === 0 ? "#d4a24c" : "rgba(243,234,211,.25)",
                  }}
                >
                  <h3 className="display" style={{ margin: 0, fontSize: "1.25rem" }}>
                    <span className="num" style={{ color: "var(--gold)" }}>{`0${i + 1}`}</span>{" "}
                    {t(`landing.features.${f}.title`)}
                  </h3>
                  <p style={{ margin: "0.35rem 0 0", color: "#d6dde3", lineHeight: 1.55 }}>
                    {t(`landing.features.${f}.body`)}
                  </p>
                </li>
              ))}
            </ol>
          </div>
          <div
            aria-hidden="true"
            style={{
              position: "absolute",
              insetInlineEnd: 18,
              top: "20%",
              bottom: "20%",
              width: 3,
              background: "rgba(243,234,211,.2)",
              borderRadius: 3,
            }}
          >
            <div
              id="sky-progress"
              style={{ height: "100%", background: "var(--gold)", transformOrigin: "top", borderRadius: 3 }}
            />
          </div>
        </section>

        {/* ---------------- ROADMAP (horizontal scroll) ---------------- */}
        <section
          id="roadmap"
          aria-labelledby="road-title"
          style={{
            position: "relative",
            minHeight: "100svh",
            background: "linear-gradient(180deg,#2a2150,#0b1b2b)",
            overflow: "hidden",
            display: "grid",
            alignContent: "center",
          }}
        >
          <h2
            id="road-title"
            className="display reveal"
            style={{ fontSize: "clamp(1.8rem,4.4vw,3rem)", margin: "0 0 1.8rem", paddingInline: "2rem" }}
          >
            {t("landing.roadmapTitle")}
          </h2>
          <div
            id="road-track"
            style={{
              display: "flex",
              gap: "1.4rem",
              paddingInline: "2rem",
              width: "max-content",
              overflowX: tier === "full" ? "visible" : "auto",
              maxWidth: tier === "full" ? undefined : "100%",
            }}
          >
            {ROADMAP.map((r, i) => (
              <article
                key={r}
                className="glass"
                data-testid="roadmap-card"
                style={{
                  width: "min(78vw, 340px)",
                  padding: "1.4rem",
                  flex: "none",
                  background: "rgba(11,27,43,.7)",
                  borderColor: "rgba(243,234,211,.25)",
                }}
              >
                <span
                  className="chip"
                  style={{ cursor: "default", color: "#f1cf8a", borderColor: "rgba(241,207,138,.5)" }}
                >
                  {t("common.comingNext")}
                </span>
                <h3 className="display" style={{ fontSize: "1.45rem", margin: "1rem 0 0.4rem" }}>
                  <span className="num" style={{ color: "var(--gold)" }}>{`0${i + 1}`}</span>{" "}
                  {t(`landing.roadmap.${r}.title`)}
                </h3>
                <p style={{ color: "#d6dde3", lineHeight: 1.55, margin: 0 }}>
                  {t(`landing.roadmap.${r}.body`)}
                </p>
              </article>
            ))}
          </div>
        </section>

        {/* ---------------- CTA ---------------- */}
        <section
          style={{
            position: "relative",
            padding: "7rem 1.5rem 6rem",
            textAlign: "center",
            background: "linear-gradient(180deg,#0b1b2b,#3b2250 70%,#b5532e)",
            overflow: "hidden",
          }}
        >
          <div className="grain" style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
          <div style={{ position: "relative", display: "grid", justifyItems: "center", gap: "1.2rem" }}>
            <div style={{ color: "var(--gold)" }}>
              <MashrabiyaLoader label="" size={72} />
            </div>
            <h2 className="display reveal" style={{ fontSize: "clamp(2rem,5vw,3.8rem)", margin: 0 }}>
              {t("landing.ctaTitle")}
            </h2>
            <p className="reveal" style={{ fontSize: "1.15rem", color: "#f0e6d0", margin: 0 }}>
              {t("landing.ctaBody")}
            </p>
            <Magnetic>
              <button className="btn reveal" onClick={() => go("/app")}>
                {t("landing.ctaPrimary")}
              </button>
            </Magnetic>
          </div>
        </section>
      </div>
    </div>
  );
}
