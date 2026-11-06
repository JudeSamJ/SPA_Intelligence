import { useEffect, useState } from "react";

export interface HeroMedia {
  mp4: boolean;
  webm: boolean;
  poster: boolean;
}
const NONE: HeroMedia = { mp4: false, webm: false, poster: false };
let cached: Promise<HeroMedia> | null = null;

/**
 * Reads /media/manifest.json (always present, committed) instead of probing for files, so a missing clip never
 * causes a 404 / console error. Failure to read the manifest simply means "no media": the procedural scene is used.
 */
export function loadHeroMedia(): Promise<HeroMedia> {
  cached ??= fetch("/media/manifest.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((j: { hero?: Partial<HeroMedia> } | null) => ({ ...NONE, ...(j?.hero ?? {}) }))
    .catch(() => NONE);
  return cached;
}

export function useHeroMedia(): HeroMedia {
  const [m, setM] = useState<HeroMedia>(NONE);
  useEffect(() => {
    let live = true;
    void loadHeroMedia().then((v) => live && setM(v));
    return () => {
      live = false;
    };
  }, []);
  return m;
}
