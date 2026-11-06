import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ago } from "@/lib/time";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-06T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

describe("ago", () => {
  it("reads just now, minutes, hours and days", () => {
    const at = (ms: number) => new Date(Date.now() - ms).toISOString();
    expect(ago(at(10_000))).toBe("just now");
    expect(ago(at(5 * 60_000))).toBe("5 min ago");
    expect(ago(at(2 * 3_600_000))).toBe("2 h ago");
    expect(ago(at(3 * 86_400_000))).toBe("3 d ago");
  });
  it("is empty for an invalid date", () => {
    expect(ago("")).toBe("");
    expect(ago("not a date")).toBe("");
  });
});
