import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, PUT } from "../app/api/proxy/[...path]/route";

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
