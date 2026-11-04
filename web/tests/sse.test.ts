import { describe, expect, it } from "vitest";
import { parseSse } from "@/lib/sse";

describe("parseSse", () => {
  it("parseSse handles events split across chunks", () => {
    const a = parseSse('event: token\r\ndata: {"text": "Hel', "");
    expect(a.events).toEqual([]);

    const b = parseSse('lo"}\r\n\r\nevent: tool_call\r\ndata: {"name": "search_canon", "args": {}}\r\n', a.carry);
    expect(b.events).toEqual([{ event: "token", data: { text: "Hello" } }]);

    const c = parseSse("\r\nevent: done\r\ndata: {}\r\n\r\n", b.carry);
    expect(c.events).toEqual([
      { event: "tool_call", data: { name: "search_canon", args: {} } },
      { event: "done", data: {} },
    ]);
    expect(c.carry).toBe("");
  });

  it("handles LF delimiters, a delimiter split between chunks, and multi-line data", () => {
    const a = parseSse('event: token\ndata: {"text":\n', "");
    const b = parseSse('data: "x"}\n', a.carry);
    expect(b.events).toEqual([]);
    const c = parseSse("\n", b.carry);
    expect(c.events).toEqual([{ event: "token", data: { text: "x" } }]);
  });

  it("does not end an event early when a CRLF is split between chunks", () => {
    const a = parseSse('event: token\r\ndata: {"text": "a"}\r', "");
    const b = parseSse("\n", a.carry);
    expect([...a.events, ...b.events]).toEqual([]);
    const c = parseSse("\r\n", b.carry);
    expect(c.events).toEqual([{ event: "token", data: { text: "a" } }]);
  });

  it("ignores ping comments, unknown fields and malformed blocks", () => {
    const { events, carry } = parseSse(
      ": ping - 2026-11-04 10:00:00\r\n\r\n" +
        "id: 1\r\nretry: 15000\r\nevent: usage\r\ndata: {\"turn\": {}, \"total\": {}}\r\n\r\n" +
        "data: {\"no\": \"event name\"}\r\n\r\n" +
        "event: token\r\ndata: not json\r\n\r\n",
      "",
    );
    expect(events).toEqual([{ event: "usage", data: { turn: {}, total: {} } }]);
    expect(carry).toBe("");
  });
});
