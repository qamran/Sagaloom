import { describe, expect, it } from "vitest";
import { readEvents } from "@/lib/readSse";
import type { SseEvent } from "@/lib/types";

const sse = (event: string, data: unknown) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
function res(chunks: string[], end: "close" | "drop" = "close"): Response {
  const enc = new TextEncoder();
  let i = 0;
  return {
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) return { done: false, value: enc.encode(chunks[i++]) };
          if (end === "drop") throw new TypeError("network error");
          return { done: true, value: undefined };
        },
      }),
    },
  } as unknown as Response;
}

describe("readEvents", () => {
  it("yields parsed events and returns done", async () => {
    const seen: SseEvent[] = [];
    const out = await readEvents(
      res([sse("node", { name: "check", phase: "start" }), sse("done", { thread_id: "t1" }), sse("node", { name: "x", phase: "end" })]),
      (e) => seen.push(e),
    );
    expect(out).toBe("done");
    expect(seen.map((e) => e.event)).toEqual(["node", "done"]);
  });

  it("returns error on an error event", async () => {
    const out = await readEvents(res([sse("error", { message: "boom", retryable: false })]), () => undefined);
    expect(out).toBe("error");
  });

  it("returns null when the body ends or drops early", async () => {
    expect(await readEvents(res([sse("node", { name: "a", phase: "start" })]), () => undefined)).toBeNull();
    expect(await readEvents(res([sse("node", { name: "a", phase: "start" })], "drop"), () => undefined)).toBeNull();
  });
});
