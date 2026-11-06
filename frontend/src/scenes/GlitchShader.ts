/**
 * WebGL image glitch (ogl, lazy-loaded): RGB channel split, scanlines, noise, row-displacement blocks, heat-haze
 * shimmer and mouse parallax over a source canvas. All uniforms are driven from GSAP. Used ONLY on the hero and
 * route transitions, never on data.
 */
export interface GlitchHandle {
  uniforms: { uIntensity: { value: number }; uMouse: { value: [number, number] }; uTime: { value: number } };
  setSource: (c: HTMLCanvasElement) => void;
  resize: () => void;
  render: (t: number) => void;
  destroy: () => void;
}

const vertex = /* glsl */ `
attribute vec2 uv; attribute vec2 position; varying vec2 vUv;
void main(){ vUv = uv; gl_Position = vec4(position, 0., 1.); }`;

const fragment = /* glsl */ `
precision highp float;
uniform sampler2D tMap; uniform float uTime; uniform float uIntensity; uniform vec2 uMouse; uniform vec2 uRes;
varying vec2 vUv;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main(){
  vec2 uv = vUv;
  uv += (uMouse - 0.5) * 0.014;                                   // pointer parallax
  float hz = smoothstep(0.5, 0.0, uv.y);                          // heat-haze near the horizon
  uv.x += sin(uv.y * 90. + uTime * 1.6) * 0.0016 * hz;
  float row = floor(uv.y * 26.);
  float tick = floor(uTime * 9.);
  float g = step(0.78, hash(vec2(row, tick))) * uIntensity;       // glitch blocks
  uv.x += (hash(vec2(row, tick + 3.)) - 0.5) * 0.14 * g;
  float s = 0.0008 + 0.006 * uIntensity;                          // RGB split
  vec3 col = vec3(texture2D(tMap, uv + vec2(s, 0.)).r, texture2D(tMap, uv).g, texture2D(tMap, uv - vec2(s, 0.)).b);
  col *= 1. - uIntensity * 0.14 * (0.5 + 0.5 * sin(uv.y * uRes.y * 1.4)); // scanlines
  col += (hash(uv * uRes + uTime) - 0.5) * 0.04 * (0.4 + uIntensity);     // grain
  gl_FragColor = vec4(col, 1.);
}`;

export async function createGlitch(
  canvas: HTMLCanvasElement,
  source: HTMLCanvasElement,
): Promise<GlitchHandle | null> {
  try {
    const { Renderer, Program, Mesh, Triangle, Texture } = await import("ogl");
    const renderer = new Renderer({
      canvas,
      alpha: false,
      dpr: Math.min(window.devicePixelRatio || 1, 1.5),
      antialias: false,
    });
    const gl = renderer.gl;
    const texture = new Texture(gl, {
      image: source,
      generateMipmaps: false,
      minFilter: gl.LINEAR,
      magFilter: gl.LINEAR,
    });
    const uniforms = {
      tMap: { value: texture },
      uTime: { value: 0 },
      uIntensity: { value: 0 },
      uMouse: { value: [0.5, 0.5] as [number, number] },
      uRes: { value: [1, 1] as [number, number] },
    };
    const program = new Program(gl, { vertex, fragment, uniforms });
    const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });
    const resize = () => {
      // ogl writes pixel sizes into canvas.style; restore CSS sizing first so we measure the real layout box
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      const r = canvas.getBoundingClientRect();
      renderer.setSize(Math.max(2, r.width), Math.max(2, r.height));
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      uniforms.uRes.value = [gl.drawingBufferWidth, gl.drawingBufferHeight];
    };
    resize();
    let alive = true;
    return {
      uniforms: uniforms as unknown as GlitchHandle["uniforms"],
      setSource: (c) => {
        texture.image = c;
        texture.needsUpdate = true;
      },
      resize,
      render: (t) => {
        if (!alive) return;
        uniforms.uTime.value = t;
        renderer.render({ scene: mesh });
      },
      // Do NOT lose the context here: the same <canvas> can be re-used by a remount (React StrictMode); the
      // browser reclaims the context when the canvas leaves the DOM.
      destroy: () => {
        alive = false;
      },
    };
  } catch {
    return null; // no WebGL: caller falls back to the static canvas
  }
}
