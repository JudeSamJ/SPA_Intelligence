import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";
import { jsonResponse } from "../test/helpers";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({
            status: "ok",
            llm_configured: true,
            model: "m",
            llm_calls_made: 0,
            llm_call_cap: 40,
          }),
        ),
    );
    expect((await api.health()).status).toBe("ok");
  });

  it("maps the server error shape to ApiError(code, message, status)", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ error: { code: "not_extracted", message: "Not extracted yet." } }, 409),
        ),
    );
    const err = await api.contract("x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "not_extracted", message: "Not extracted yet." });
  });

  it("falls back to a generic error for non-JSON failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>boom</html>", { status: 502 })));
    await expect(api.contracts()).rejects.toMatchObject({ status: 502, code: "http_error" });
  });

  it("reports network failures as code 'network' with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.contracts()).rejects.toMatchObject({ status: 0, code: "network" });
  });

  it("posts JSON bodies and never sends keys", async () => {
    const f = vi
      .fn()
      .mockResolvedValue(jsonResponse({ answer: "a", refused: false, citations: [], tool_calls: [] }));
    vi.stubGlobal("fetch", f);
    await api.chat("id1", "hello", []);
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/contracts/id1/chat");
    expect(JSON.parse(init.body as string)).toEqual({ message: "hello", history: [] });
    expect(JSON.stringify(init)).not.toMatch(/api[_-]?key|authorization/i);
  });
});
