import { useEffect, useState } from "react";
import { authEnabled, authedBlob } from "./token";

/** A URL an <img> can use: unchanged when sign-in is off, otherwise a blob URL fetched with the bearer token. */
export function useAuthedSrc(url: string): string | null {
  const [blob, setBlob] = useState<{ url: string; obj: string } | null>(null);
  const need = authEnabled();
  useEffect(() => {
    if (!need) return;
    let alive = true;
    let obj = "";
    authedBlob(url)
      .then((b) => {
        obj = URL.createObjectURL(b);
        if (alive) setBlob({ url, obj });
      })
      .catch(() => alive && setBlob(null));
    return () => {
      alive = false;
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [url, need]);
  return need ? (blob?.url === url ? blob.obj : null) : url;
}
