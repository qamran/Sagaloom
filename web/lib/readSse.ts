import { parseSse } from "./sse";
import type { SseEvent } from "./types";

/**
 * Reads a streamed response to its first `done` or `error` event, handing every event (those two
 * included) to `onEvent` in arrival order. Returns which one ended it, or null when the body
 * closed or the connection dropped before either arrived.
 */
export async function readEvents(res: Response, onEvent: (ev: SseEvent) => void): Promise<"done" | "error" | null> {
  let ended: "done" | "error" | null = null;
  if (!res.body) return null;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let carry = "";
  try {
    while (ended === null) {
      const { done, value } = await reader.read();
      if (done) break;
      const parsed = parseSse(decoder.decode(value, { stream: true }), carry);
      carry = parsed.carry;
      for (const ev of parsed.events) {
        if (ended !== null) break;
        if (ev.event === "done") ended = "done";
        else if (ev.event === "error") ended = "error"; // terminal: no `done` follows it
        onEvent(ev);
      }
    }
  } catch {
    /* the connection dropped mid-stream: the caller sees null */
  }
  return ended;
}

/** FastAPI's `detail`: a string as is, a validation list as "edited.title: <msg>; …". */
export async function detailOf(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (!Array.isArray(body.detail)) return "";
    return body.detail
      .map((d: { loc?: unknown[]; msg?: unknown }) => {
        const field = (d.loc ?? [])
          .filter((p) => typeof p === "string" && p !== "body" && p !== "decisions")
          .join(".");
        return field ? `${field}: ${String(d.msg)}` : String(d.msg);
      })
      .join("; ");
  } catch {
    return "";
  }
}
