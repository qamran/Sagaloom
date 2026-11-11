import "server-only";
import type { PublicPreview } from "./types";

/** How long the web server keeps the preview before asking the API again (the fixture is frozen). */
const REVALIDATE_S = 3600;
const TIMEOUT_MS = 5000;

const isPreview = (body: unknown): body is PublicPreview => {
  const b = body as Partial<PublicPreview> | null;
  return (
    !!b &&
    Array.isArray(b.messages) &&
    Array.isArray(b.entries) &&
    !!b.pending_interrupt &&
    Array.isArray(b.pending_interrupt.proposals) &&
    typeof b.pending_interrupt.checks === "object"
  );
};

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
