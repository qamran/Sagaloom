import "server-only";
import type { PublicPreview } from "./types";

/** How long the web server keeps the preview before asking the API again (the fixture is frozen). */
const REVALIDATE_S = 3600;
// A hung API must not stall `/`: after this the page renders without the preview.
const TIMEOUT_MS = 2000;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isStr = (v: unknown): v is string => typeof v === "string";
const isFact = (f: unknown) => isObj(f) && isStr(f.key) && isStr(f.value) && Array.isArray(f.refs);
const isEntry = (e: unknown) =>
  isObj(e) && isStr(e.id) && isStr(e.title) && isStr(e.type) && isStr(e.body) && isStr(e.status) &&
  Array.isArray(e.facts) && e.facts.every(isFact);
const isProposal = (p: unknown) =>
  isObj(p) && isStr(p.proposal_id) && isStr(p.action) && isStr(p.world_id) &&
  (p.after === null || (isObj(p.after) && Array.isArray(p.after.facts) && p.after.facts.every(isFact)));
const isCheck = (c: unknown) =>
  isObj(c) && Array.isArray(c.flags) && c.flags.every(isObj) && Array.isArray(c.dependents);

/** The shapes the home page renders; anything else is treated as no preview (never a 500). */
function isPreview(body: unknown): body is PublicPreview {
  if (!isObj(body) || !isObj(body.pending_interrupt)) return false;
  const { messages, entries } = body;
  const { proposals, checks } = body.pending_interrupt;
  return (
    Array.isArray(messages) && messages.every((m) => isObj(m) && isStr(m.role) && isStr(m.content)) &&
    Array.isArray(entries) && entries.every(isEntry) &&
    Array.isArray(proposals) && proposals.every(isProposal) &&
    isObj(checks) && Object.values(checks).every(isCheck)
  );
}

/**
 * The home page's recorded Velmar example (M5 §5.7), read on the web server straight from the API
 * with the shared secret, which therefore never reaches the browser; only the returned data does.
 * Cached by Next for an hour. Any failure gives null: the home page then renders without it.
 */
export async function getPreview(): Promise<PublicPreview | null> {
  const secret = process.env.API_SHARED_SECRET;
  if (!secret) return null;
  const url = `${process.env.API_URL ?? "http://localhost:8000"}/api/public/preview`;
  try {
    const res = await fetch(url, {
      headers: { "x-sagaloom-secret": secret },
      next: { revalidate: REVALIDATE_S },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) {
      console.error("home: preview request failed", url, res.status);
      return null;
    }
    const body: unknown = await res.json();
    return isPreview(body) ? body : null;
  } catch (cause) {
    // The URL and the cause only: the request headers carry the shared secret.
    console.error("home: preview unavailable", url, cause instanceof Error ? cause.message : cause);
    return null;
  }
}
