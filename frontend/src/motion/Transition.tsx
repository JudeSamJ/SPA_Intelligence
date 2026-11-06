import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { drawSunsetScene } from "../scenes/drawScene";
import { createGlitch, type GlitchHandle } from "../scenes/GlitchShader";
import { usePrefs } from "../state/prefs";
import { glitchText } from "./effects";
import { gsap } from "./registry";

type Go = (to: string) => void;
const Ctx = createContext<Go>(() => {});
export const useGo = () => useContext(Ctx);

interface P {
  x: number;
  y: number;
  r: number;
  v: number;
  a: number;
}

/**
 * Route transition: a canvas particle SANDSTORM sweeps across and covers the screen, the route changes while it is
 * covered (a WebGL-glitched golden-hour image shows briefly), then the storm clears. Reduced effects: no overlay.
 */
export function TransitionProvider({ children }: { children: ReactNode }) {
  const nav = useNavigate();
  const loc = useLocation();
  const { tier, dir, theme } = usePrefs();
  const canvas = useRef<HTMLCanvasElement>(null);
  const glCanvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<HTMLCanvasElement | null>(null);
  const glitch = useRef<GlitchHandle | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    if (tier !== "full") return;
    const s = document.createElement("canvas");
    s.width = 1280;
    s.height = 720;
    drawSunsetScene(s, theme);
    scene.current = s;
    glitch.current?.setSource(s);
  }, [tier, theme]);

  useEffect(() => () => glitch.current?.destroy(), []);

  const go = useCallback<Go>(
    (to) => {
      if (to === loc.pathname || busy.current) return nav(to);
      if (tier === "reduced") return nav(to);
      const c = canvas.current;
      const ctx = c?.getContext("2d");
      if (!c || !ctx) return nav(to);
      busy.current = true;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      c.width = window.innerWidth * dpr;
      c.height = window.innerHeight * dpr;
      c.style.display = "block";
      const W = c.width,
        H = c.height;
      const sign = dir === "rtl" ? -1 : 1;
      const n = tier === "full" ? 650 : 220;
      const parts: P[] = Array.from({ length: n }, () => ({
        x: Math.random(),
        y: Math.random(),
        r: 1 + Math.random() * 3.2,
        v: 0.6 + Math.random() * 0.9,
        a: 0.35 + Math.random() * 0.55,
      }));
      const state = { p: 0, glitch: 0 };

      const draw = () => {
        ctx.clearRect(0, 0, W, H);
        const wall = gsap.utils.clamp(0, 1, (state.p - 0.35) / 0.55);
        if (wall > 0) {
          const g = ctx.createLinearGradient(0, 0, 0, H);
          g.addColorStop(0, `rgba(59,34,80,${wall})`);
          g.addColorStop(0.6, `rgba(181,83,46,${wall})`);
          g.addColorStop(1, `rgba(212,162,76,${wall})`);
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, W, H);
        }
        ctx.fillStyle = "#e8c689";
        for (const q of parts) {
          const x =
            (sign === 1 ? state.p * 1.5 * q.v - 0.25 + q.x * 0.6 : 1.25 - state.p * 1.5 * q.v - q.x * 0.6) *
            W;
          ctx.globalAlpha = q.a;
          ctx.fillRect(x, q.y * H, q.r * dpr * 3.4, q.r * dpr * 0.8);
        }
        ctx.globalAlpha = 1;
      };
      const g = glCanvas.current;
      if (tier === "full" && g && scene.current && !glitch.current) {
        void createGlitch(g, scene.current).then((h) => (glitch.current = h));
      }
      const tick = (t: number) => {
        draw();
        const h = glitch.current;
        if (h && g) {
          h.uniforms.uIntensity.value = state.glitch;
          h.render(t);
        }
      };
      gsap.ticker.add(tick);

      const tl = gsap.timeline({
        onComplete: () => {
          gsap.ticker.remove(tick);
          c.style.display = "none";
          if (g) g.style.opacity = "0";
          busy.current = false;
        },
      });
      tl.to(state, { p: 1, duration: 0.55, ease: "power2.in" })
        .add(() => {
          nav(to);
          window.scrollTo(0, 0);
          if (g && glitch.current) gsap.set(g, { opacity: 1 });
        })
        .to(state, { glitch: 1, duration: 0.12, ease: "none" })
        .to(state, { glitch: 0, duration: 0.22, ease: "power2.out" })
        .add(() => {
          requestAnimationFrame(() => {
            const title = document.querySelector<HTMLElement>("[data-glitch-title]");
            if (title) glitchText(title, tier);
          });
        })
        .to(g ?? {}, { opacity: 0, duration: 0.2 }, "<0.1")
        .to(state, { p: 0, duration: 0.6, ease: "power2.out" });
    },
    [nav, loc.pathname, tier, dir],
  );

  const value = useMemo(() => go, [go]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <canvas
        ref={canvas}
        aria-hidden="true"
        data-testid="sandstorm"
        style={{
          display: "none",
          position: "fixed",
          inset: 0,
          width: "100%",
          height: "100%",
          zIndex: 70,
          pointerEvents: "none",
        }}
      />
      <canvas
        ref={glCanvas}
        aria-hidden="true"
        style={{
          opacity: 0,
          position: "fixed",
          inset: 0,
          width: "100%",
          height: "100%",
          zIndex: 69,
          pointerEvents: "none",
          display: tier === "full" ? "block" : "none",
        }}
      />
    </Ctx.Provider>
  );
}

/** Page content entrance on every route change (also covers browser back/forward). */
export function RouteFade({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  const section = pathname.split("/")[1] ?? ""; // fade whole pages only; in-app tab/contract switches animate locally
  const { tier } = usePrefs();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const tw = gsap.fromTo(
      el,
      { opacity: 0, y: tier === "reduced" ? 0 : 14 },
      {
        opacity: 1,
        y: 0,
        duration: tier === "reduced" ? 0.15 : 0.55,
        ease: "power3.out",
        clearProps: "transform,opacity",
      },
    );
    return () => void tw.kill();
  }, [section, tier]);
  return <div ref={ref}>{children}</div>;
}
