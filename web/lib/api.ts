import type {
  Entry,
  GuardLogRow,
  MemoryPayload,
  ModelRole,
  ModelsPayload,
  PromptRecord,
  SettingsPatch,
  ToolInfo,
  SettingsPayload,
  StudioData,
  ThreadState,
  LastRun,
  MentionRef,
  ThreadSummary,
  World,
} from "./types";

// The browser only ever talks to the Next.js proxy, which injects the shared secret.
// The API's export tool repeats this prefix; tests/proxyPrefix.test.ts keeps the two equal.
export const PROXY_BASE = "/api/proxy";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The API's 401 detail when the request carries no valid Clerk session token. */
export const SIGN_IN_REQUIRED = "sign in required";
/** What to show for a 503: a new account is still being set up, or Clerk is unreachable. */
export const ACCOUNT_UNAVAILABLE =
  "Setting up your account, or the account service is unavailable — try again.";
// Pages that render without a session: a 401 seen there must not redirect, or sign-in would reload itself.
const PUBLIC_PAGE = /^\/(sign-in|sign-up)(\/|$)|^\/$/;
const RETRY_503_MS = 1500;

/** Shown when Clerk has a session but the API keeps refusing its token (wrong address, issuer, clock). */
export const SESSION_REJECTED =
  "You're signed in, but the API rejected the session. Check that you opened the app at its configured address, then sign in again.";
const REDIRECT_KEY = "sagaloom.signInRedirectAt";
const BOUNCE_WINDOW_MS = 30_000;
// The redirect this page itself started: parallel requests on one page must not count as a bounce.
let redirectedAt: string | null = null;

function readRedirectAt(): string | null {
  try {
    return sessionStorage.getItem(REDIRECT_KEY);
  } catch {
    return null; // storage unavailable: always redirect
  }
}

function writeRedirectAt(value: string): void {
  try {
    sessionStorage.setItem(REDIRECT_KEY, value);
  } catch {
    /* storage unavailable: always redirect */
  }
}

/**
 * Sends the author to sign-in, and back here afterwards, when the API says the session is missing or
 * expired (401 "sign in required"). The other 401 ("unauthorised") is a bad shared secret: a server
 * misconfiguration that signing in cannot fix, so it never redirects.
 *
 * The API also answers "sign in required" for a token it rejects while Clerk still holds a valid
 * session; sign-in then bounces straight back. So a second "sign in required" within 30 s of the last
 * redirect does not redirect again: it answers "rejected" and the caller shows `SESSION_REJECTED`.
 * After the window, a later attempt redirects again.
 */
export function handleAuthStatus(
  status: number,
  detail: string | undefined,
): "redirected" | "rejected" | null {
  if (status !== 401 || detail !== SIGN_IN_REQUIRED) return null;
  if (PUBLIC_PAGE.test(location.pathname)) return null;
  const last = readRedirectAt();
  if (last !== null && last === redirectedAt) return "redirected"; // already leaving this page
  if (last !== null && Date.now() - Number(last) < BOUNCE_WINDOW_MS) return "rejected";
  redirectedAt = String(Date.now());
  writeRedirectAt(redirectedAt);
  // A full page load on purpose: this runs outside React (no router here), and it lets Clerk's handshake run.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  location.assign("/sign-in?redirect_url=" + encodeURIComponent(location.pathname + location.search));
  return "redirected";
}

async function detailFrom(res: Response): Promise<string | undefined> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail))
      return body.detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join("; ") || undefined;
  } catch {
    // no JSON body: the status line is enough
  }
  return undefined;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const send = () =>
    fetch(`${PROXY_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  let res = await send();
  // The first request after sign-up provisions the account and may answer 503 once; a GET is safe to repeat.
  const isGet = (init?.method ?? "GET").toUpperCase() === "GET";
  if (res.status === 503 && isGet) {
    await res.body?.cancel();
    await wait(RETRY_503_MS);
    res = await send();
  }
  if (!res.ok) {
    const detail = await detailFrom(res);
    const auth = handleAuthStatus(res.status, detail);
    const message =
      auth === "rejected"
        ? SESSION_REJECTED
        : res.status === 503
          ? ACCOUNT_UNAVAILABLE
          : `${res.status} ${res.statusText || "request failed"}`;
    throw new ApiError(res.status, message, detail);
  }
  return (await res.json()) as T;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const getWorlds = () => request<World[]>("/worlds");
export const createWorld = (name: string) => request<World>("/worlds", post({ name }));
export const getEntries = (worldId: string) =>
  request<Entry[]>(`/worlds/${encodeURIComponent(worldId)}/entries`);
export const getEntry = (worldId: string, id: string) =>
  request<Entry>(`/worlds/${encodeURIComponent(worldId)}/entries/${encodeURIComponent(id)}`);
export const getMentions = (worldId: string, id: string) =>
  request<MentionRef[]>(
    `/worlds/${encodeURIComponent(worldId)}/entries/${encodeURIComponent(id)}/mentions`,
  );
export const createThread = (worldId: string) =>
  request<{ thread_id: string }>("/threads", post({ world_id: worldId }));
export const getThread = (id: string) => request<ThreadState>(`/threads/${encodeURIComponent(id)}`);
export const getReviewThreads = (worldId: string) =>
  request<ThreadSummary[]>(`/threads?pending=true&world_id=${encodeURIComponent(worldId)}`);
export const getStudio = () => request<StudioData>("/studio");
export const getModels = () => request<ModelsPayload>("/settings/models");
export const putModel = (role: ModelRole, model: string) =>
  request<ModelsPayload>("/settings/models", { method: "PUT", body: JSON.stringify({ role, model }) });
export const getLlmLog = (threadId: string) =>
  request<PromptRecord[]>(`/threads/${encodeURIComponent(threadId)}/llm-log`);
export const getSettings = () => request<SettingsPayload>("/settings");
export const putSettings = (patch: SettingsPatch) =>
  request<SettingsPayload>("/settings", { method: "PUT", body: JSON.stringify(patch) });
export const getTools = () => request<ToolInfo[]>("/tools");
export const getGuardLog = (limit = 20) => request<GuardLogRow[]>(`/guard/log?limit=${limit}`);

/** The Markdown zip download for a world (R11.5.4), through the proxy. */
export function exportUrl(worldId: string, excludeSecrets: boolean): string {
  const base = `${PROXY_BASE}/worlds/${encodeURIComponent(worldId)}/export?format=md`;
  return excludeSecrets ? `${base}&exclude_secrets=true` : base;
}

export const getMemory = (worldId: string) =>
  request<MemoryPayload>(`/worlds/${encodeURIComponent(worldId)}/memory`);
/** Forgets a preference; for a list key pass the `item` to drop only that line. */
export const forgetMemory = (worldId: string, key: string, item?: string) =>
  request<MemoryPayload>(
    `/worlds/${encodeURIComponent(worldId)}/memory?key=${encodeURIComponent(key)}${
      item === undefined ? "" : `&item=${encodeURIComponent(item)}`
    }`,
    { method: "DELETE" },
  );
export const getImports = (worldId: string) =>
  request<ThreadSummary[]>(`/threads?world_id=${encodeURIComponent(worldId)}&kind=import`);
export const getThreads = () => request<ThreadSummary[]>("/threads");
export const getLastRun = (threadId: string) =>
  request<LastRun>(`/threads/${encodeURIComponent(threadId)}/runs/last`);
