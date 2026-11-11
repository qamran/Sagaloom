import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

// Clerk is never called from tests: `auth()` is a stub, and `clerkMiddleware` just runs the handler
// with that stub so web/proxy.ts's own decisions can be checked.
const { authMock } = vi.hoisted(() => ({ authMock: vi.fn() }));
vi.mock("@clerk/nextjs/server", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@clerk/nextjs/server")>();
  return {
    auth: authMock,
    createRouteMatcher: actual.createRouteMatcher,
    clerkMiddleware:
      (handler: (auth: unknown, req: NextRequest, ev: unknown) => unknown) => (req: NextRequest, ev: unknown) =>
        handler(authMock, req, ev),
  };
});

import { GET, POST } from "../app/api/proxy/[...path]/route";
import proxy from "../proxy";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
const signedIn = (token = "tok_user_abc") =>
  authMock.mockResolvedValue({ userId: "user_1", getToken: vi.fn(async () => token) });
const signedOut = () => {
  const redirectToSignIn = vi.fn(() => new Response(null, { status: 307, headers: { location: "/sign-in" } }));
  authMock.mockResolvedValue({ userId: null, getToken: vi.fn(async () => null), redirectToSignIn });
  return redirectToSignIn;
};

describe("API proxy route: Clerk token forwarding", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.stubEnv("API_URL", "http://api.test");
    vi.stubEnv("API_SHARED_SECRET", "s3cret-for-test");
    authMock.mockReset();
    fetchMock = vi.fn(async () => new Response("[]", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards bearer token", async () => {
    signedIn("tok_user_abc");
    const res = await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx("worlds"));

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/worlds");
    const sent = new Headers(init.headers);
    expect(sent.get("authorization")).toBe("Bearer tok_user_abc");
    expect(sent.get("x-sagaloom-secret")).toBe("s3cret-for-test");
  });

  it("401 without token on non-public path, API not called", async () => {
    signedOut();
    const res = await POST(
      new Request("http://localhost:3000/api/proxy/threads", { method: "POST", body: "{}" }),
      ctx("threads"),
    );

    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ detail: "sign in required" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("public preview path forwarded without token", async () => {
    signedIn();
    const res = await GET(
      new Request("http://localhost:3000/api/proxy/public/preview", { headers: { authorization: "Bearer from-browser" } }),
      ctx("public", "preview"),
    );

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/public/preview");
    const sent = new Headers(init.headers);
    expect(sent.has("authorization")).toBe(false);
    expect(sent.get("x-sagaloom-secret")).toBe("s3cret-for-test");
    expect(authMock).not.toHaveBeenCalled();
  });

  it("never copies the cookie header upstream", async () => {
    signedIn("tok_server_side");
    await GET(
      new Request("http://localhost:3000/api/proxy/worlds", {
        headers: { cookie: "__session=browser-cookie", authorization: "Bearer browser-made-up" },
      }),
      ctx("worlds"),
    );

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const sent = new Headers(init.headers);
    expect(sent.has("cookie")).toBe(false);
    // The browser's own Authorization is never passed on: only the server-side Clerk token.
    expect(sent.get("authorization")).toBe("Bearer tok_server_side");
  });

  it("still answers 500 for a missing shared secret before asking Clerk", async () => {
    vi.stubEnv("API_SHARED_SECRET", "");
    signedIn();
    const res = await GET(new Request("http://localhost:3000/api/proxy/worlds"), ctx("worlds"));

    expect(res.status).toBe(500);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("web/proxy.ts: which requests need a signed-in user", () => {
  beforeEach(() => authMock.mockReset());
  const call = (path: string, headers: Record<string, string> = {}) =>
    (proxy as unknown as (req: NextRequest, ev: unknown) => Promise<Response | undefined>)(
      new NextRequest(`http://localhost:3000${path}`, { headers }),
      {},
    );

  it("sends a signed-out visitor of an app page to sign-in", async () => {
    const redirectToSignIn = signedOut();
    const res = await call("/canon/ent_0007", { accept: "text/html" });

    expect(redirectToSignIn).toHaveBeenCalledWith({ returnBackUrl: "http://localhost:3000/canon/ent_0007" });
    expect(res?.status).toBe(307);
  });

  it("answers 401 JSON to a signed-out API proxy request", async () => {
    const redirectToSignIn = signedOut();
    const res = await call("/api/proxy/worlds");

    expect(res?.status).toBe(401);
    expect(await res?.json()).toEqual({ detail: "sign in required" });
    expect(redirectToSignIn).not.toHaveBeenCalled();
  });

  it.each(["/", "/sign-in", "/sign-in/factor-one", "/sign-up", "/sign-up/verify-email-address", "/api/proxy/public/preview"])(
    "lets a signed-out visitor through to the public %s",
    async (path) => {
      const redirectToSignIn = signedOut();
      const res = await call(path);

      expect(res).toBeUndefined();
      expect(redirectToSignIn).not.toHaveBeenCalled();
    },
  );

  it("lets a signed-in user through to app pages and the API proxy", async () => {
    signedIn();
    expect(await call("/canon")).toBeUndefined();
    expect(await call("/api/proxy/worlds")).toBeUndefined();
  });
});
