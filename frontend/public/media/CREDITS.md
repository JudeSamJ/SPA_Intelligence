# Media and asset credits

**No third-party video, photo or illustration is bundled.** Every visual in the app is original work generated in code:

| Visual | How it is made | Licence |
|---|---|---|
| Dunes, ripple texture, Palm Jumeirah-style line art, skyline with a Burj-style stepped tower, dhow, falcon, date palm | Hand-written SVG and seeded generators in `src/scenes/art.ts` | Original (project licence) |
| Golden-hour hero scene and WebGL glitch / heat-haze | Canvas 2D drawing + an `ogl` fragment shader (`src/scenes/drawScene.ts`, `GlitchShader.ts`) | Original |
| Mashrabiya star lattice | Generic 8-point-star geometry drawn as SVG | Original (traditional geometry, no copyrighted artwork) |
| Sandstorm, gold dust, coin burst, stars, grain | Canvas / DOM particles and an SVG noise filter | Original |
| Sample contracts (`samples/*.pdf`) | `scripts/generate_samples.py`; fictional developers, buyers and projects | Original / synthetic |

No real developer logos, brands or project names are used. District names (Dubai Marina, Palm Jumeirah, Downtown, Business Bay, Yas Island, Saadiyat) are public place names used only as decoration/context.

## Hero video (optional, you supply it)

`hero.mp4` / `hero.webm` / `hero-poster.jpg` are **not** in the repo. Without them the hero uses the procedural scene above.
To add your own licensed footage: `scripts/prepare_media.sh path/to/clip.mp4` (encodes to < 6 MB each and flips the flags in
`manifest.json`). **Then record the clip's source and licence here before committing:**

| File | Source / URL | Licence | Attribution required |
|---|---|---|---|
| _(none yet)_ | | | |

Do not hotlink stock video; do not commit footage whose licence you cannot verify.

## Libraries and fonts

| Item | Licence |
|---|---|
| GSAP 3.15 + all plugins (ScrollTrigger, ScrollSmoother, SplitText, MorphSVG, DrawSVG, ScrambleText, InertiaPlugin, Physics2D/PhysicsProps, MotionPath, Flip, Draggable, Observer, CustomEase/Wiggle/Bounce, EasePack, TextPlugin, ScrollToPlugin). GSDevTools and MotionPathHelper are dev-only and excluded from production builds. | GSAP Standard "no charge" licence: https://gsap.com/standard-license (please read it for your use case) |
| React, React Router, TanStack Query, react-i18next, Recharts, ogl, Tailwind CSS, Vite, Vitest | MIT |
| Fraunces, Inter, Noto Kufi Arabic, Tajawal (self-hosted via `@fontsource`) | SIL Open Font License 1.1 |
