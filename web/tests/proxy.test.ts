import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST, PUT } from "../app/api/proxy/[...path]/route";

// A signed-in user: these tests are about the shared secret and pass-through (Clerk: proxyAuth.test.ts).
vi.mock("@clerk/nextjs/server", () => ({ auth: async () => ({ getToken: async () => "tok_test" }) }));

describe("secret-injecting proxy", () => {
  beforeEach(() => {
    process.env.API_URL = "http://api.test";
    process.env.API_SHARED_SECRET = "s3cret-for-test";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
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

  it("passes a binary download through with its content-disposition", async () => {
    const bytes = new Uint8Array([80, 75, 3, 4, 0, 255, 128]);
    const fetchMock = vi.fn(
      async () =>
        new Response(bytes, {
          status: 200,
          headers: {
            "content-type": "application/zip",
            "content-disposition": 'attachment; filename="velmar.zip"',
          },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(new Request("http://localhost:3000/api/proxy/worlds/velmar/export?format=md"), {
      params: Promise.resolve({ path: ["worlds", "velmar", "export"] }),
    });

    expect(res.headers.get("content-type")).toBe("application/zip");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="velmar.zip"');
    expect(new Uint8Array(await res.arrayBuffer())).toEqual(bytes);
  });

  it("drops a browser-sent x-forwarded-for by default, and adds none", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const ctx = { params: Promise.resolve({ path: ["worlds"] }) };

    await GET(new Request("http://localhost:3000/api/proxy/worlds", { headers: { "x-forwarded-for": "9.9.9.9" } }), ctx);
    await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx);

    const [[, withIp], [, without]] = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(new Headers(withIp.headers).has("x-forwarded-for")).toBe(false);
    expect(new Headers(without.headers).has("x-forwarded-for")).toBe(false);
  });

  it("forwards the incoming x-forwarded-for only when TRUST_FORWARDED_FOR is true", async () => {
    vi.stubEnv("TRUST_FORWARDED_FOR", "true");
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const ctx = { params: Promise.resolve({ path: ["worlds"] }) };

    await GET(new Request("http://localhost:3000/api/proxy/worlds", { headers: { "x-forwarded-for": "9.9.9.9, 10.0.0.1" } }), ctx);
    await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx);

    const [[, withIp], [, without]] = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(new Headers(withIp.headers).get("x-forwarded-for")).toBe("9.9.9.9, 10.0.0.1");
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

  it("forwards DELETE with its query string and the secret", async () => {
    const fetchMock = vi.fn(async () => new Response('{"preferences":{}}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await DELETE(
      new Request("http://localhost:3000/api/proxy/worlds/w/memory?key=notes&item=no%20gods", { method: "DELETE" }),
      { params: Promise.resolve({ path: ["worlds", "w", "memory"] }) },
    );

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/worlds/w/memory?key=notes&item=no%20gods");
    expect(init.method).toBe("DELETE");
    expect(new Headers(init.headers).get("x-sagaloom-secret")).toBe(process.env.API_SHARED_SECRET);
    expect(res.status).toBe(200);
  });
});

describe("proxy failure modes", () => {
  beforeEach(() => {
    process.env.API_URL = "http://api.test";
    process.env.API_SHARED_SECRET = "s3cret-for-test";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });
  const ctx = () => ({ params: Promise.resolve({ path: ["worlds"] }) });

  it("answers 500 JSON when the shared secret is empty", async () => {
    for (const value of ["", undefined]) {
      if (value === undefined) delete process.env.API_SHARED_SECRET;
      else process.env.API_SHARED_SECRET = value;
      const fetchMock = vi.fn(async () => new Response("{}"));
      vi.stubGlobal("fetch", fetchMock);
      const res = await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx());
      expect(res.status).toBe(500);
      expect(res.headers.get("content-type")).toContain("application/json");
      expect(await res.json()).toEqual({ detail: "API_SHARED_SECRET is not set on the web server" });
      expect(fetchMock).not.toHaveBeenCalled();
    }
  });

  it("answers 502 JSON when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx());
    expect(res.status).toBe(502);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual({ detail: "The API is not reachable" });
  });

  it("answers 400 JSON when the request body cannot be read", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    const req = new Request("http://localhost:3000/api/proxy/worlds", { method: "POST", body: "{}" });
    vi.spyOn(req, "text").mockRejectedValue(new TypeError("body stream aborted"));
    const res = await POST(req, ctx());
    expect(res.status).toBe(400);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual({ detail: "Could not read the request body" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("logs the cause of an unreachable API", async () => {
    const cause = new TypeError("fetch failed");
    vi.stubGlobal("fetch", vi.fn(async () => { throw cause; }));
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx());
    expect(errorSpy).toHaveBeenCalledTimes(1);
    const args = errorSpy.mock.calls[0];
    expect(args).toContain(cause);
    expect(args).toContain("http://api.test/api/worlds");
    for (const arg of args) {
      const text = arg instanceof Error ? `${arg.message} ${arg.stack}` : `${String(arg)} ${JSON.stringify(arg)}`;
      expect(text).not.toContain("s3cret-for-test");
    }
  });

  it("passes a text/event-stream response through unbuffered", async () => {
    const enc = new TextEncoder();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const body = new ReadableStream<Uint8Array>({
      async start(c) {
        c.enqueue(enc.encode('event: token\ndata: {"t":"a"}\n\n'));
        await gate; // the second chunk exists only after the first was read downstream
        c.enqueue(enc.encode("event: done\ndata: {}\n\n"));
        c.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } })),
    );
    const res = await GET(new Request("http://localhost:3000/api/proxy/threads/t/stream"), ctx());
    expect(res.headers.get("content-type")).toBe("text/event-stream");
    const reader = res.body!.getReader();
    const dec = new TextDecoder();
    const first = await reader.read();
    expect(dec.decode(first.value)).toBe('event: token\ndata: {"t":"a"}\n\n');
    release();
    const second = await reader.read();
    expect(dec.decode(second.value)).toBe("event: done\ndata: {}\n\n");
    expect((await reader.read()).done).toBe(true);
  });
});

describe("proxy path hardening", () => {
  beforeEach(() => {
    process.env.API_URL = "http://api.test";
    process.env.API_SHARED_SECRET = "s3cret-for-test";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
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

  it("answers the path guard in JSON without calling the API", async () => {
    const fetchMock = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new Request("http://localhost:3000/api/proxy/x"), {
      params: Promise.resolve({ path: ["worlds", ".."] }),
    });
    expect(res.status).toBe(400);
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(await res.json()).toEqual({ detail: "Bad path" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
