import type {
  Entry,
  GuardLogRow,
  ModelRole,
  ModelsPayload,
  PromptRecord,
  SettingsPatch,
  ToolInfo,
  SettingsPayload,
  StudioData,
  ThreadState,
  ThreadSummary,
  World,
} from "./types";

// The browser only ever talks to the Next.js proxy, which injects the shared secret.
const BASE = "/api/proxy";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail))
        detail = body.detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join("; ") || undefined;
    } catch {
      // no JSON body: the status line is enough
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText || "request failed"}`, detail);
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
export const createThread = (worldId: string) =>
  request<{ thread_id: string }>("/threads", post({ world_id: worldId }));
export const getThread = (id: string) => request<ThreadState>(`/threads/${encodeURIComponent(id)}`);
export const getPendingThreads = () => request<ThreadSummary[]>("/threads?pending=true");
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
  const base = `${BASE}/worlds/${encodeURIComponent(worldId)}/export?format=md`;
  return excludeSecrets ? `${base}&exclude_secrets=true` : base;
}
