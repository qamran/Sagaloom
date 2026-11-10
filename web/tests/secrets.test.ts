import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SHOW_SECRETS_KEY, listenedWorldCount, useShowSecrets } from "@/lib/secrets";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe("useShowSecrets", () => {
  it("is off by default and always off without a world id", () => {
    expect(renderHook(() => useShowSecrets("w1")).result.current[0]).toBe(false);
    const { result } = renderHook(() => useShowSecrets(undefined));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(false);
  });

  it("persists on under the per-world sessionStorage key", () => {
    const { result } = renderHook(() => useShowSecrets("w1"));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w1"))).toBe("true");
    expect(SHOW_SECRETS_KEY("w1")).toBe("sagaloom.showSecrets.w1");
  });

  it("reads false for another world", () => {
    const first = renderHook(() => useShowSecrets("w1"));
    act(() => first.result.current[1](true));
    expect(renderHook(() => useShowSecrets("w2")).result.current[0]).toBe(false);
  });

  it("keeps two hook users in sync", () => {
    const a = renderHook(() => useShowSecrets("w1"));
    const b = renderHook(() => useShowSecrets("w1"));
    act(() => a.result.current[1](true));
    expect(b.result.current[0]).toBe(true);
    act(() => b.result.current[1](false));
    expect(a.result.current[0]).toBe(false);
  });

  it("falls back to memory when sessionStorage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useShowSecrets("w9"));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
  });
});

describe("useShowSecrets with only setItem failing", () => {
  it("still works for the page", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useShowSecrets("w8"));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
  });
});

describe("useShowSecrets fails closed", () => {
  it("turning secrets off while storage fails reads off", () => {
    const { result } = renderHook(() => useShowSecrets("w7"));
    act(() => result.current[1](true));
    expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w7"))).toBe("true");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    act(() => result.current[1](false));
    expect(result.current[0]).toBe(false);
  });

  it("drops a world's listener set when the last subscriber leaves", () => {
    const before = listenedWorldCount();
    const a = renderHook(() => useShowSecrets("w-listen"));
    const b = renderHook(() => useShowSecrets("w-listen"));
    expect(listenedWorldCount()).toBe(before + 1);
    a.unmount();
    expect(listenedWorldCount()).toBe(before + 1);
    b.unmount();
    expect(listenedWorldCount()).toBe(before);
  });
});
