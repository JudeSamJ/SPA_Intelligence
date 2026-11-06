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
import { MashrabiyaBand, MashrabiyaLoader } from "../scenes/Mashrabiya";
import { Marquee } from "../scenes/Marquee";
import { Palm } from "../scenes/Palm";
import { Skyline, SKY_D } from "../scenes/Skyline";
import { usePrefs } from "../state/prefs";

/**
 * First-pass smoothness: GSAP initialises DrawSVG (path lengths) and MotionPath (path parsing) lazily, the first time a
 * tween renders. In a scrubbed scene that lands in the middle of the user's first downward scroll as a hitch, while
 * later passes (and scrolling back up) reuse the cached values. Rendering the whole timeline once while idle moves
 * that cost out of the scroll.
 */
function prewarm(tl: gsap.core.Timeline, resync?: () => void): () => void {
  const id = window.setTimeout(() => {
    tl.progress(1, true).progress(0, true);
    if (resync) resync();
    else tl.scrollTrigger?.update();
  }, 900);
  return () => window.clearTimeout(id);
}

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

  // --- palm scene: the island GROWS out of the sea. Time-based, NOT scroll-scrubbed and NOT pinned. ------------
  // Earlier versions scrubbed the drawing to the scroll position inside a pinned section; any scroll speed or direction
  // change then showed up directly as skipped/glitchy frames. Now the scroll only *starts* the animation (once, when the
  // scene enters the viewport); it plays over a fixed duration on the GSAP ticker, so scroll behaviour cannot affect it.
  useMotion(
    root,
    ({ tier: tr, rtl }) => {
      if (!ready || tr === "reduced") return;
      const q = gsap.utils.selector(root.current!);
      const fronds = q("#palm .frond") as unknown as SVGPathElement[];
      // initial (hidden) state
      gsap.set(q("#palm .draw"), { drawSVG: "0%" });
      gsap.set(fronds, {
        scale: 0,
        opacity: 0,
        svgOrigin: (_i: number, el: Element) => (el as SVGElement).dataset.origin ?? "400 600",
      });
      gsap.set(q("#palm .palm-copy > *"), { opacity: 0, y: 24 });
      gsap.set(["#plane", ".palm-glow"], { opacity: 0 });
      gsap.set(q("#palm .ripple"), { scale: 0.4, opacity: 0, svgOrigin: "400 752" });

      const intro = gsap.timeline({ paused: true, defaults: { ease: "power2.out" } });
      intro
        .to(".palm-glow", { opacity: 1, duration: 2.4, ease: "sine.inOut" }, 0)
        .to(q("#palm .palm-copy > *"), { opacity: 1, y: 0, duration: 0.9, stagger: 0.28 }, 0.1)
        .to(q("#palm .trunk"), { drawSVG: "100%", duration: 1.5, ease: "power2.inOut" }, 0.3)
        // fronds sprout from the trunk, base to tip, with a soft spring
        .to(
          fronds,
          {
            scale: 1,
            opacity: 1,
            duration: 0.8,
            ease: "back.out(1.5)",
            stagger: { each: 0.1, from: "start" },
          },
          1.0,
        )
        .to(q("#palm .crescent"), { drawSVG: "100%", duration: 2, ease: "power2.inOut" }, 2.5)
        .to(q("#palm .ring"), { drawSVG: "100%", duration: 1.8, stagger: 0.3, ease: "power2.inOut" }, 3.0)
        .to("#plane", { opacity: 1, duration: 0.5 }, 4.4)
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
            duration: 4.2,
            ease: "power1.inOut",
          },
          4.4,
        )
        .to("#palm-marker", { attr: { r: 9 }, duration: 0.6, ease: "back.out(2)" }, 5.4);

      // ambient sea ripples + marker pulse: cheap, looping, only while the scene is on screen
      const ambient = gsap.timeline({ paused: true });
      ambient.to(
        q("#palm .ripple"),
        {
          scale: 2.4,
          opacity: 0,
          duration: 3.6,
          ease: "sine.out",
          stagger: { each: 1.2, repeat: -1 },
          startAt: { opacity: 0.55, scale: 0.4 },
        },
        0,
      );

      const st = ScrollTrigger.create({
        trigger: "#palm",
        start: "top 70%",
        end: "bottom 10%",
        onEnter: () => {
          if (intro.progress() === 0) intro.play();
          ambient.play();
        },
        onEnterBack: () => ambient.play(),
        onLeave: () => ambient.pause(),
        onLeaveBack: () => ambient.pause(),
      });
      const stopWarm = prewarm(intro);
      return () => {
        stopWarm();
        st.kill();
        intro.kill();
        ambient.kill();
      };
    },
    [ready],
  );

  // --- skyline: pinned; each step's card appears beside the tower tier it lights up, alternating sides ---------
  useMotion(
    root,
    ({ tier: tr, desktop, rtl }) => {
      if (!ready || tr === "reduced") return;
      const R = root.current!;
      const q = gsap.utils.selector(R);
      const wide = desktop && tr === "full" && window.innerWidth >= 1000;
      const cards = q("[data-feature]") as HTMLElement[];
      const conns = q("[data-conn]") as HTMLElement[];
      const content = R.querySelector<HTMLElement>("#sky-content")!;
      const ol = content.querySelector<HTMLElement>("ol")!;
      const sideOf = (i: number) => ((i % 2 === 0) === !rtl ? "left" : "right");
      const clear = () => {
        for (const prop of ["position", "inset", "maxWidth", "pointerEvents"])
          ol.style.removeProperty(
            prop === "maxWidth" ? "max-width" : prop === "pointerEvents" ? "pointer-events" : prop,
          );
        cards.forEach((c) =>
          ["position", "width", "top", "left", "right"].forEach((p) => c.style.removeProperty(p)),
        );
        conns.forEach((c) => (c.style.display = "none"));
      };
      // Place each card beside the tower tier of its band, measured from the real SVG (relative to #sky-content).
      // Batched to avoid layout thrashing on this heavy page: ONE read phase, then writes, then one read, then writes.
      let lastKey = "";
      const place = () => {
        if (!wide) return clear();
        // ---- read phase (no style writes before this point)
        const cr = content.getBoundingClientRect();
        const key = `${Math.round(cr.width)}x${Math.round(cr.height)}x${cards.map((c) => c.offsetHeight).join(",")}`;
        if (key === lastKey) return; // layout unchanged since the last placement (ScrollTrigger refreshes often at load)
        const t0 = R.querySelector<SVGGElement>('#burj [data-tier="0"]')!.getBoundingClientRect();
        const tiers = [...R.querySelectorAll<SVGGElement>("#burj [data-tier]")].map((g) => ({
          band: Number(g.getAttribute("data-band")),
          r: g.getBoundingClientRect(),
        }));
        const gap = 64;
        const plan = cards.map((_, i) => {
          const rects = tiers.filter((t) => t.band === i).map((t) => t.r);
          const side = sideOf(i);
          const room = side === "left" ? t0.left - cr.left - gap - 24 : cr.right - t0.right - gap - 24;
          const w = Math.max(220, Math.min(340, room));
          const centre =
            (Math.min(...rects.map((r) => r.top)) + Math.max(...rects.map((r) => r.bottom))) / 2 - cr.top;
          // each connector reaches its own tier edge (upper tiers are narrower than the base)
          const reach =
            side === "left"
              ? Math.min(...rects.map((r) => r.left)) - (t0.left - gap)
              : t0.right + gap - Math.max(...rects.map((r) => r.right));
          const x = side === "left" ? t0.left - cr.left - gap - w : t0.right - cr.left + gap;
          return { side, w, centre, reach, x };
        });
        // ---- write phase 1: widths and horizontal positions
        ol.style.position = "absolute";
        ol.style.inset = "0";
        ol.style.maxWidth = "none";
        ol.style.pointerEvents = "none";
        cards.forEach((c, i) => {
          const pl = plan[i]!;
          c.style.position = "absolute";
          c.style.width = `${pl.w}px`;
          c.style.left = `${pl.x}px`;
          c.style.right = "auto";
          const k = conns[i]!;
          k.style.display = "block";
          k.style.width = `${Math.max(gap, pl.reach)}px`;
          k.style.left = pl.side === "left" ? "100%" : "auto";
          k.style.right = pl.side === "left" ? "auto" : "100%";
          k.style.transformOrigin = pl.side === "left" ? "left center" : "right center";
        });
        // ---- read phase 2 (card heights depend on the widths just written), then write phase 2: vertical positions
        const heights = cards.map((c) => c.offsetHeight);
        cards.forEach((c, i) => {
          c.style.top = `${Math.min(Math.max(plan[i]!.centre - heights[i]! / 2, 96), cr.height - heights[i]! - 56)}px`;
        });
        lastKey = key;
      };
      place();
      ScrollTrigger.addEventListener("refreshInit", place);
      void document.fonts?.ready.then(place);
      if (wide) gsap.set(cards, { autoAlpha: 0 });

      const TOTAL = 0.6 + (FEATURES.length - 1) * 1.25 + 0.8 + 0.7; // = the timeline's real length (5.85)
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: "#skyline",
          start: "top top",
          end: wide ? "+=380%" : "+=150%",
          pin: wide,
          scrub: tr === "full" ? 1.2 : 0.6,
          anticipatePin: tr === "full" ? 0 : 1,
          invalidateOnRefresh: true,
          snap: wide
            ? { snapTo: "labels", duration: { min: 0.25, max: 0.7 }, delay: 0.05, ease: "power1.inOut" }
            : undefined,
        },
      });
      tl.addLabel("start", 0)
        .fromTo(
          "#sky-scene",
          { "--sky-top": "#2d2a5a", "--sky-bot": "#f0a35a" },
          { "--sky-top": "#0b1b2b", "--sky-bot": "#3b2250", duration: TOTAL },
          0,
        )
        .fromTo("#sky-progress", { scaleY: 0 }, { scaleY: 1, duration: TOTAL }, 0);
      FEATURES.forEach((_, i) => {
        const T = 0.6 + i * 1.25;
        const side = sideOf(i);
        tl.addLabel(`f${i}`, T);
        // highlight by scale + border, never by fading text (keeps contrast >= 4.5:1 at every scroll position)
        tl.to(
          cards.filter((_, j) => j !== i),
          { scale: 0.97, borderColor: "rgba(243,234,211,.25)", duration: 0.25 },
          T,
        ).to(cards[i]!, { scale: 1.03, borderColor: "#d4a24c", duration: 0.35 }, T);
        if (wide) {
          tl.fromTo(
            cards[i]!,
            { autoAlpha: 0, x: side === "left" ? -80 : 80 },
            { autoAlpha: 1, x: 0, duration: 0.7, ease: "power2.out" },
            T,
          ).fromTo(conns[i]!, { scaleX: 0 }, { scaleX: 1, duration: 0.45, ease: "power2.out" }, T + 0.25);
        }
        // light this band's floors, glow the tier, then let the glow settle as the next band takes over
        tl.to(
          q(`#burj [data-win][data-band="${i}"]`),
          { opacity: 0.95, stagger: { each: 0.03, from: "random" }, duration: 0.7 },
          T,
        )
          .to(q(`#burj [data-glow][data-band="${i}"]`), { opacity: 0.6, duration: 0.45 }, T)
          .to(q(`#burj [data-glow][data-band="${i}"]`), { opacity: 0.22, duration: 0.7 }, T + 0.8)
          .to(
            (q("[data-win]:not(#burj [data-win])") as Element[]).slice(i * 14, i * 14 + 30),
            { opacity: 0.8, stagger: 0.02, duration: 0.5 },
            T + 0.2,
          );
      });
      tl.to("#burj-beacon", { opacity: 1, duration: 0.3 }, TOTAL - 0.7).addLabel("end", TOTAL);
      const stopWarm = prewarm(tl);
      return () => {
        stopWarm();
        ScrollTrigger.removeEventListener("refreshInit", place);
        clear();
        tl.scrollTrigger?.kill();
      };
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
          anticipatePin: tr === "full" ? 0 : 1,
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
            style={{ position: "absolute", insetInline: 0, bottom: 0, height: "90%", color: "#150f24" }}
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
                "linear-gradient(180deg, rgba(11,27,43,.62), rgba(11,27,43,.12) 55%, rgba(11,27,43,.5))",
              pointerEvents: "none",
            }}
          />
          <div
            id="sky-content"
            style={{
              position: "relative",
              padding: "6.5rem 2rem 3rem",
              display: "grid",
              gap: "1.2rem",
              alignContent: "start",
              minHeight: "100svh",
            }}
          >
            <h2
              id="sky-title"
              className="display"
              style={{
                fontSize: "clamp(1.8rem,3.6vw,2.8rem)",
                margin: 0,
                maxWidth: "18ch",
                textShadow: "0 2px 18px rgba(11,27,43,.85)",
              }}
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
                    position: "relative",
                    padding: "0.9rem 1.1rem",
                    background: "rgba(11,27,43,.86)",
                    borderColor: i === 0 ? "#d4a24c" : "rgba(243,234,211,.25)",
                    pointerEvents: "auto",
                  }}
                >
                  <span
                    data-conn
                    aria-hidden="true"
                    style={{
                      display: "none",
                      position: "absolute",
                      top: "50%",
                      height: 2,
                      background: "linear-gradient(90deg,#d4a24c,#ffe3a0)",
                      borderRadius: 2,
                    }}
                  />
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
