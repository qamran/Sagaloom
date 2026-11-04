import type { SseEvent } from "./types";

/**
 * Parse one chunk of a `text/event-stream` body (sse-starlette sends `\r\n` line endings and
 * `: ping` comments). `carry` is the unfinished tail of the previous chunk; pass the returned
 * `carry` into the next call. Blocks without an `event:` name or with invalid JSON are skipped.
 */
export function parseSse(chunk: string, carry: string): { events: SseEvent[]; carry: string } {
  let raw = carry + chunk;
  // A trailing \r may be the first half of a \r\n split across chunks: hold it back.
  const heldCr = raw.endsWith("\r");
  if (heldCr) raw = raw.slice(0, -1);
  const blocks = raw.replace(/\r\n?/g, "\n").split("\n\n");
  const rest = (blocks.pop() ?? "") + (heldCr ? "\r" : "");
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let name = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") name = value;
      else if (field === "data") data.push(value);
    }
    if (!name) continue;
    try {
      events.push({ event: name, data: JSON.parse(data.join("\n") || "{}") } as SseEvent);
    } catch {
      /* malformed block: skip it rather than break the stream */
    }
  }
  return { events, carry: rest };
}
