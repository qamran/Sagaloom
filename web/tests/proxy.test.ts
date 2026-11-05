import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST, PUT } from "../app/api/proxy/[...path]/route";

describe("secret-injecting proxy", () => {
  beforeEach(() => {
    process.env.API_URL = "http://api.test";
    process.env.API_SHARED_SECRET = "s3cret-for-test";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards to the API with the secret and passes the body through", async () => {
    const fetchMock = vi.fn(async () => new Response('[{"id":1}]', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(new Request("http://localhost:3000/api/proxy/worlds"), {
      params: Promise.resolve({ path: ["worlds"] }),
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/worlds");
    expect(new Headers(init.headers).get("x-sagaloom-secret")).toBe(
      process.env.API_SHARED_SECRET,
    );
    expect(await res.text()).toBe('[{"id":1}]');
  });

  it("forwards the incoming x-forwarded-for header, and sends none when absent", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const ctx = { params: Promise.resolve({ path: ["worlds"] }) };

    await GET(new Request("http://localhost:3000/api/proxy/worlds", { headers: { "x-forwarded-for": "9.9.9.9" } }), ctx);
    await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx);

    const [[, withIp], [, without]] = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(new Headers(withIp.headers).get("x-forwarded-for")).toBe("9.9.9.9");
    expect(new Headers(without.headers).has("x-forwarded-for")).toBe(false);
  });

  it("forwards PUT with its JSON body and the secret", async () => {
    const fetchMock = vi.fn(async () => new Response('{"mapping":{}}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await PUT(
      new Request("http://localhost:3000/api/proxy/settings/models", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: '{"role":"judge","model":"openai/gpt-6.1-terra"}',
      }),
      { params: Promise.resolve({ path: ["settings", "models"] }) },
    );

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/settings/models");
    expect(init.method).toBe("PUT");
    expect(init.body).toBe('{"role":"judge","model":"openai/gpt-6.1-terra"}');
    expect(new Headers(init.headers).get("x-sagaloom-secret")).toBe(process.env.API_SHARED_SECRET);
    expect(res.status).toBe(200);
  });
});

describe("proxy path hardening", () => {
  beforeEach(() => {
    process.env.API_URL = "http://api.test";
    process.env.API_SHARED_SECRET = "s3cret-for-test";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([["."], [".."], ["%2e%2e"], ["%2E"]])("rejects the dot segment %s with 400 for every method", async (seg) => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    for (const handler of [GET, POST, PUT]) {
      const res = await handler(new Request("http://localhost:3000/api/proxy/x", { method: "POST" }), {
        params: Promise.resolve({ path: ["threads", seg, "messages"] }),
      });
      expect(res.status).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
