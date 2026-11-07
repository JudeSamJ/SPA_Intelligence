/** Where the API client gets its bearer token. Empty when sign-in is not configured (AUTH_MODE=off on the server). */
type Provider = () => Promise<string | null>;
let provider: Provider | null = null;

export const setTokenProvider = (p: Provider | null) => {
  provider = p;
};
export const authEnabled = () => provider !== null;
export const getToken = async (): Promise<string | null> => (provider ? provider() : null);

/** fetch with the bearer token, for resources an <img> or <a> cannot authenticate (page images, PDF, CSV). */
export async function authedBlob(url: string): Promise<Blob> {
  const token = await getToken();
  const res = await fetch(url, token ? { headers: { Authorization: `Bearer ${token}` } } : undefined);
  if (!res.ok) throw new Error(`Request failed (${res.status}).`);
  return res.blob();
}

/** Open a protected URL in a new tab, or save it as a file. */
export async function authedOpen(url: string, filename?: string): Promise<void> {
  const obj = URL.createObjectURL(await authedBlob(url));
  if (filename) {
    const a = document.createElement("a");
    a.href = obj;
    a.download = filename;
    a.click();
  } else {
    window.open(obj, "_blank", "noopener");
  }
  setTimeout(() => URL.revokeObjectURL(obj), 60_000);
}
