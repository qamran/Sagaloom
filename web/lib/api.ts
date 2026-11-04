import type {
  Entry,
  ModelRole,
  ModelsPayload,
  PromptRecord,
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
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText || "request failed"}`);
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
