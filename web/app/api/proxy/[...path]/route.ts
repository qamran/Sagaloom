import { auth } from "@clerk/nextjs/server";

export const dynamic = "force-dynamic";

function jsonError(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

function decodeSafe(seg: string): string {
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}

async function forward(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  // A dot segment would let a request climb out of /api (the URL parser resolves it).
  if (path.some((seg) => [".", ".."].includes(decodeSafe(seg)))) {
    return jsonError(400, "Bad path");
  }
  const secret = process.env.API_SHARED_SECRET;
  if (!secret) return jsonError(500, "API_SHARED_SECRET is not set on the web server");
  const base = process.env.API_URL ?? "http://localhost:8000";
  const search = new URL(req.url).search;
  const url = `${base}/api/${path.map(encodeURIComponent).join("/")}${search}`;

  const headers = new Headers();
  headers.set("x-sagaloom-secret", secret);
  // The user's Clerk session token, read on the server from the session cookie. Headers are built
  // from scratch, so an Authorization or Cookie the browser sent is never passed on. Every path
  // needs one: the home page reads /api/public/preview on the server (lib/preview.ts), not through here.
  const token = await (await auth()).getToken();
  if (!token) return jsonError(401, "sign in required");
  headers.set("authorization", `Bearer ${token}`);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  // The API rate-limits per client. A route handler cannot tell an edge's X-Forwarded-For from
  // one the browser made up, so it is passed on only when the deployment opts in (its edge
  // overwrites or appends the caller's address); otherwise none is sent.
  if (process.env.TRUST_FORWARDED_FOR === "true") {
    const forwardedFor = req.headers.get("x-forwarded-for");
    if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  }
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  let body: string | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    try {
      body = await req.text();
    } catch {
      return jsonError(400, "Could not read the request body");
    }
  }
  let upstream: Response;
  try {
    upstream = await fetch(url, { method: req.method, headers, body, cache: "no-store" });
  } catch (cause) {
    // The target URL and the cause only: the headers carry the shared secret and the user's token.
    console.error("proxy: API fetch failed", url, cause);
    return jsonError(502, "The API is not reachable");
  }

  const out = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) out.set("content-type", upstreamType);
  const disposition = upstream.headers.get("content-disposition");
  if (disposition) out.set("content-disposition", disposition);
  out.set("cache-control", "no-cache, no-transform");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
