import { useEffect, useRef, useState } from "react";
import { EASE } from "../motion/ease";
import { gsap, ScrollTrigger } from "../motion/registry";
import { useMotion } from "../motion/mm";
import { usePrefs } from "../state/prefs";
import { Dunes } from "./Dunes";
import { drawSunsetScene } from "./drawScene";
import { createGlitch, type GlitchHandle } from "./GlitchShader";
import { Stars } from "./Stars";
import { useHeroMedia } from "./useHeroMedia";

/**
 * Hero background, in priority order:
 *  1. looping muted <video> (dunes -> skyline at golden hour) if /media/hero.* exists, tier is full, and the
 *     user has not asked for reduced data; paused when off-screen
 *  2. WebGL glitch over the procedural golden-hour scene (full tier)
 *  3. the same scene as a static canvas + parallax SVG dunes (lite / reduced / no WebGL)
 */
export function HeroBackdrop() {
  const root = useRef<HTMLDivElement>(null);
  const src = useRef<HTMLCanvasElement>(null);
  const gl = useRef<HTMLCanvasElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const handle = useRef<GlitchHandle | null>(null);
  const { theme, tier } = usePrefs();
  const [glReady, setGlReady] = useState(false);
  const media = useHeroMedia();
  const hasVideo = media.mp4 || media.webm;
  const hasPoster = media.poster;
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  const useVideo = hasVideo && tier === "full" && !saveData;

  // procedural scene (source texture) - redrawn on theme change
  useEffect(() => {
    const c = src.current;
    if (!c) return;
    c.width = 1600;
    c.height = 900;
    drawSunsetScene(c, theme);
    handle.current?.setSource(c);
  }, [theme]);

  // WebGL glitch layer (full tier only, no video)
  useEffect(() => {
    if (tier !== "full" || useVideo || !gl.current || !src.current) return;
    let dead = false;
    void createGlitch(gl.current, src.current).then((h) => {
      if (dead || !h) return void h?.destroy();
      handle.current = h;
      setGlReady(true);
    });
    return () => {
      dead = true;
      handle.current?.destroy();
      handle.current = null;
      setGlReady(false);
    };
  }, [tier, useVideo]);

  useMotion(
    root,
    ({ tier: tr }) => {
      if (tr !== "full") return;
      const h = handle.current;
      const el = root.current!;
      // slow cinematic push-in (ExpoScaleEase) on the scene layers; settles and stays put
      gsap.fromTo(
        [src.current, gl.current].filter(Boolean),
        { scale: 1 },
        { scale: 1.06, duration: 24, ease: EASE.expoScale(1, 1.06) },
      );
      let visible = true;
      const io = new IntersectionObserver(([e]) => {
        visible = !!e?.isIntersecting;
        const v = video.current;
        if (v) void (visible ? v.play().catch(() => {}) : v.pause());
      });
      io.observe(el);
      // heat-haze shimmer (feTurbulence + feDisplacementMap), animated with GSAP
      const turb = el.querySelector("[data-haze]");
      if (turb)
        gsap.to(turb, {
          attr: { baseFrequency: "0.01 0.05" },
          duration: 6,
          yoyo: true,
          repeat: -1,
          ease: "sine.inOut",
        });
      // mouse-reactive parallax on dune layers + shader uniform
      const layers = gsap.utils.toArray<SVGElement>("[data-dune]", el);
      const setters = layers.map((l) => ({
        x: gsap.quickTo(l, "x", { duration: 0.8, ease: "power3.out" }),
        d: Number(l.dataset.depth ?? 0.5),
      }));
      const move = (e: PointerEvent) => {
        const nx = e.clientX / window.innerWidth - 0.5;
        setters.forEach((s) => s.x(-nx * 60 * s.d));
        if (h) h.uniforms.uMouse.value = [e.clientX / window.innerWidth, 1 - e.clientY / window.innerHeight];
      };
      window.addEventListener("pointermove", move);
      // glitch bursts: short and rare (< 3 flashes / second), plus an entrance glitch that settles clean
      let bursts: gsap.core.Timeline | undefined;
      if (h) {
        h.uniforms.uIntensity.value = 1;
        bursts = gsap
          .timeline({ repeat: -1, repeatDelay: 5 })
          .to(h.uniforms.uIntensity, { value: 0, duration: 1.1, ease: "power3.out" }, 0.05)
          .to(h.uniforms.uIntensity, { value: 0.7, duration: 0.12, ease: "none" }, "+=3.4")
          .to(h.uniforms.uIntensity, { value: 0, duration: 0.3, ease: "power2.out" });
      }
      const tick = (t: number) => {
        if (h && visible) h.render(t);
      };
      gsap.ticker.add(tick);
      const onResize = () => h?.resize();
      window.addEventListener("resize", onResize);
      const st = ScrollTrigger.create({
        trigger: el,
        start: "top top",
        end: "bottom top",
        scrub: true,
        onUpdate: (s) =>
          h && (h.uniforms.uIntensity.value = Math.max(h.uniforms.uIntensity.value, s.progress * 0.25)),
      });
      return () => {
        io.disconnect();
        window.removeEventListener("pointermove", move);
        window.removeEventListener("resize", onResize);
        gsap.ticker.remove(tick);
        bursts?.kill();
        st.kill();
      };
    },
    [glReady, useVideo],
  );

  const staticVisible = !(tier === "full" && glReady && !useVideo);
  return (
    <div
      ref={root}
      aria-hidden="true"
      className="grain"
      style={{ position: "absolute", inset: 0, overflow: "hidden", background: "#0b1b2b" }}
    >
      <canvas
        ref={src}
        data-testid="hero-scene"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: staticVisible && !useVideo ? "block" : "none",
        }}
      />
      <canvas
        ref={gl}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          display: tier === "full" && !useVideo ? "block" : "none",
        }}
      />
      {useVideo && (
        <video
          ref={video}
          muted
          loop
          playsInline
          autoPlay
          preload="metadata"
          poster={hasPoster ? "/media/hero-poster.jpg" : undefined}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        >
          {media.webm && <source src="/media/hero.webm" type="video/webm" />}
          {media.mp4 && <source src="/media/hero.mp4" type="video/mp4" />}
        </video>
      )}
      {theme === "dusk" && <Stars count={tier === "lite" ? 28 : 70} />}
      {tier !== "reduced" && <Dunes layers={tier === "lite" ? 3 : 5} haze={tier === "full"} />}
      {/* scrim: keeps the headline above 4.5:1 regardless of what the scene/video shows */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(180deg, rgba(11,27,43,.78) 0%, rgba(11,27,43,.55) 38%, rgba(11,27,43,.1) 70%, rgba(11,27,43,.55) 100%)",
        }}
      />
    </div>
  );
}
