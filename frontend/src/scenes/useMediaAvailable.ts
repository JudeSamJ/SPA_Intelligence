import { useEffect, useState } from "react";

/** Vite's dev server answers missing files with index.html (200). So check the Content-Type, not just the status. */
export function useMediaAvailable(url: string, prefix: "video/" | "image/"): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    let live = true;
    fetch(url, { method: "HEAD" })
      .then((r) => live && setOk(r.ok && (r.headers.get("content-type") ?? "").startsWith(prefix)))
      .catch(() => live && setOk(false));
    return () => {
      live = false;
    };
  }, [url, prefix]);
  return ok;
}
