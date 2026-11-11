import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCOUNT_UNAVAILABLE, ApiError, createWorld, getWorlds, handleAuthStatus, SESSION_REJECTED } from "@/lib/api";

// What a previous page wrote when it sent the author to sign-in.
const REDIRECT_KEY = "sagaloom.signInRedirectAt";
const redirectedAgo = (ms: number) => sessionStorage.setItem(REDIRECT_KEY, String(Date.now() - ms));

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let assign: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;
const at = (pathname: string, search = "") => vi.stubGlobal("location", { pathname, search, assign });

beforeEach(() => {
  assign = vi.fn();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  at("/canon/ent_0007", "?tab=facts");
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("API 401 and 503 handling", () => {
  it("a 401 'sign in required' redirects to /sign-in with the current path", async () => {
    fetchMock.mockResolvedValue(json(401, { detail: "sign in required" }));

    await expect(getWorlds()).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledWith("/sign-in?redirect_url=%2Fcanon%2Fent_0007%3Ftab%3Dfacts");
  });

  it("a 401 'unauthorised' (bad shared secret) is an error, never a redirect", async () => {
    fetchMock.mockResolvedValue(json(401, { detail: "unauthorised" }));

    const err = await getWorlds().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect((err as ApiError).detail).toBe("unauthorised");
    expect(assign).not.toHaveBeenCalled();
  });

  it.each(["/sign-in", "/sign-in/factor-one", "/sign-up", "/"])(
    "does not redirect again while already on the public page %s",
    async (pathname) => {
      at(pathname);
      fetchMock.mockResolvedValue(json(401, { detail: "sign in required" }));

      await expect(getWorlds()).rejects.toBeInstanceOf(ApiError);
      expect(assign).not.toHaveBeenCalled();
    },
  );

  it("retries a GET once after a 503, so a first load after sign-up recovers", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(json(503, { detail: "account service unavailable" }))
      .mockResolvedValueOnce(json(200, [{ id: "velmar" }]));

    const pending = getWorlds();
    await vi.advanceTimersByTimeAsync(1500);
    await expect(pending).resolves.toEqual([{ id: "velmar" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a GET that answers 503 twice fails with the account-service message", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(async () => json(503, { detail: "account service unavailable" }));

    const pending = getWorlds().catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1500);
    const err = await pending;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(503);
    expect((err as ApiError).message).toBe(ACCOUNT_UNAVAILABLE);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never retries a POST that answers 503", async () => {
    fetchMock.mockResolvedValue(json(503, { detail: "account service unavailable" }));

    const err = await createWorld("Aster").catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(503);
    expect((err as ApiError).message).toBe(ACCOUNT_UNAVAILABLE);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("handleAuthStatus redirects only for 'sign in required' and says what it did", () => {
    expect(handleAuthStatus(401, "sign in required")).toBe("redirected");
    expect(assign).toHaveBeenCalledTimes(1);
    expect(handleAuthStatus(401, "unauthorised")).toBeNull();
    expect(handleAuthStatus(403, "sign in required")).toBeNull();
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it("drains the first 503 body before retrying a GET", async () => {
    vi.useFakeTimers();
    const first = json(503, { detail: "account service unavailable" });
    const cancel = vi.spyOn(first.body!, "cancel");
    fetchMock.mockResolvedValueOnce(first).mockResolvedValueOnce(json(200, []));

    const pending = getWorlds();
    await vi.advanceTimersByTimeAsync(1500);
    await pending;
    expect(cancel).toHaveBeenCalled();
  });
});

describe("sign-in bounce guard", () => {
  it("a second 'sign in required' within 30 s of the last redirect shows an error instead of redirecting", async () => {
    redirectedAgo(5_000);
    fetchMock.mockResolvedValue(json(401, { detail: "sign in required" }));

    const err = await getWorlds().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe(SESSION_REJECTED);
    expect(assign).not.toHaveBeenCalled();
  });

  it("redirects again once 30 s have passed since the last redirect", async () => {
    redirectedAgo(31_000);
    fetchMock.mockResolvedValue(json(401, { detail: "sign in required" }));

    await expect(getWorlds()).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it("parallel requests on one page redirect once and are not taken for a bounce", async () => {
    fetchMock.mockImplementation(async () => json(401, { detail: "sign in required" }));

    const errs = await Promise.all([getWorlds().catch((e: unknown) => e), getWorlds().catch((e: unknown) => e)]);
    expect(assign).toHaveBeenCalledTimes(1);
    for (const e of errs) expect((e as ApiError).message).not.toBe(SESSION_REJECTED);
  });

  it("always redirects when session storage is unavailable", async () => {
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("sessionStorage", { getItem: blocked, setItem: blocked });
    fetchMock.mockImplementation(async () => json(401, { detail: "sign in required" }));

    await expect(getWorlds()).rejects.toBeInstanceOf(ApiError);
    await expect(getWorlds()).rejects.toBeInstanceOf(ApiError);
    expect(assign).toHaveBeenCalledTimes(2);
  });
});
