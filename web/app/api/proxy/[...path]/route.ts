export const dynamic = "force-dynamic";

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
  if (path.some((seg) => ["", ".", ".."].includes(decodeSafe(seg)) && seg !== "")) {
    return new Response("bad path", { status: 400 });
  }
  const base = process.env.API_URL ?? "http://localhost:8000";
  const search = new URL(req.url).search;
  const url = `${base}/api/${path.map(encodeURIComponent).join("/")}${search}`;

  const headers = new Headers();
  headers.set("x-sagaloom-secret", process.env.API_SHARED_SECRET ?? "");
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  // The API rate-limits per client: pass the caller's address along when the platform set one.
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: hasBody ? await req.text() : undefined,
    cache: "no-store",
  });

  const out = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) out.set("content-type", upstreamType);
  out.set("cache-control", "no-cache, no-transform");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
