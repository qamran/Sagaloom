import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getPreview } from "@/lib/preview";

const body = { messages: [{ role: "user", content: "hi" }], pending_interrupt: { proposals: [], checks: {} }, entries: [] };

describe("getPreview (server only)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.stubEnv("API_URL", "http://api.test");
    vi.stubEnv("API_SHARED_SECRET", "s3cret-for-test");
    fetchMock = vi.fn(async () => Response.json(body));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("accepts the API's own fixture", async () => {
    const fixture = JSON.parse(readFileSync(join(__dirname, "..", "..", "api", "sagaloom", "public", "preview.json"), "utf8"));
    fetchMock.mockResolvedValue(Response.json(fixture));
    expect(await getPreview()).toEqual(fixture);
  });

  it("gives up after 2 s so a hung API cannot stall the page", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    await getPreview();
    expect(timeout).toHaveBeenCalledWith(2000);
    expect((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].signal).toBe(timeout.mock.results[0].value);
  });

  it("asks the API with the shared secret, cached for an hour", async () => {
    expect(await getPreview()).toEqual(body);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { next?: { revalidate?: number } }];
    expect(url).toBe("http://api.test/api/public/preview");
    expect(new Headers(init.headers).get("x-sagaloom-secret")).toBe("s3cret-for-test");
    expect(new Headers(init.headers).get("authorization")).toBeNull();
    expect(init.next).toEqual({ revalidate: 3600 });
  });

  it.each([
    ["the API answers an error", () => fetchMock.mockResolvedValue(new Response("nope", { status: 500 }))],
    ["the API is down", () => fetchMock.mockRejectedValue(new TypeError("fetch failed"))],
    ["the body is not a preview", () => fetchMock.mockResolvedValue(Response.json({ detail: "x" }))],
    ["the body is not JSON", () => fetchMock.mockResolvedValue(new Response("<html>"))],
    ["an entry has no facts", () => fetchMock.mockResolvedValue(Response.json({ ...body, entries: [{ id: "e", title: "t", type: "place", body: "", status: "canon" }] }))],
    ["a check has no flags", () => fetchMock.mockResolvedValue(Response.json({ ...body, pending_interrupt: { proposals: [], checks: { p: { dependents: [] } } } }))],
    ["a message has no content", () => fetchMock.mockResolvedValue(Response.json({ ...body, messages: [{ role: "user" }] }))],
  ])("gives null when %s", async (_, arrange) => {
    arrange();
    expect(await getPreview()).toBeNull();
  });

  it("gives null without calling the API when no secret is configured", async () => {
    vi.stubEnv("API_SHARED_SECRET", "");
    expect(await getPreview()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
