import type { components } from "./api-types.gen";

// Types for the models the API publishes in its OpenAPI schema are generated: lib/api-types.gen.ts
// (`pnpm types:gen`; `pnpm types:check` fails when it is stale) and re-exported here under their old
// names. Everything else stays hand-written, mirroring api/sagaloom/web/routes.py: the SSE events,
// `ThreadSummary`, `StudioData`, the settings payloads and every `-> dict` route, because those
// routes declare no response model, so FastAPI puts no schema for them in the OpenAPI document.

type Schemas = components["schemas"];

export type Entry = Schemas["Entry"];
export type Fact = Schemas["Fact-Output"];
export type EntrySource = Schemas["EntrySource-Output"];
export type Link = Schemas["Link"];
export type World = Schemas["World"];
export type MentionRef = Schemas["MentionRef"];
export type Decision = Schemas["Decision"];

// EntryDraft only appears in the schema as a request body (Decision.edited), where defaulted fields
// are optional. A draft inside a proposal always carries aliases, facts and status, so those stay
// required; provenance stays optional (older payloads and hand-built drafts still type-check).
export type EntryDraft = Omit<Schemas["EntryDraft"], "aliases" | "facts" | "status"> & {
  aliases: string[];
  facts: Fact[];
  status: Status;
};

export type EntryType = Entry["type"];
export type Status = Entry["status"];
export type Source = Entry["source"];

export interface Proposal {
  proposal_id: string;
  action: "create" | "update" | "delete";
  world_id: string;
  entry_id: string | null;
  before: Entry | null;
  after: EntryDraft | null;
  // Server-set: the proposal came from an import (paste or fan wiki). Absent on older payloads.
  imported?: boolean;
}

export interface Flag {
  kind: "conflict" | "retcon" | "note";
  entry_id: string;
  title: string;
  fact_key: string | null;
  existing_fact: string | null;
  new_fact: string | null;
  existing_quote: string | null;
  new_quote: string | null;
  severity: "hard" | "possible" | "note" | null;
  explanation: string;
  suggested_fix: string | null;
  /** The existing side is (or may be) a secret fact: its free text is masked on the card. */
  existing_secret: boolean;
}

export interface EntryRef {
  id: string;
  title: string;
  type: EntryType;
  /** A delete-check dependent named in its text, or tied only by a link (which may be secret).
   *  Always sent by the API; optional only so hand-built results still type-check ("text"). */
  via?: "text" | "link";
}

/** Review badge, worst first (api/sagaloom/check/badge.py). */
export type Badge = "conflict" | "failed" | "possible" | "retcon" | "note" | "clear";

export interface CheckResult {
  proposal_id: string;
  verdict: "none" | "possible" | "conflict" | "failed";
  flags: Flag[];
  dependents: EntryRef[];
  /** Always sent by the API; optional only so hand-built results still type-check. */
  badge?: Badge;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

/** What the `remember` node did with one preference; render `note` and `value`, never `content`. */
export interface MemoryResult {
  key: string;
  value: string;
  stored: boolean;
  note: string;
  /** Set by the API since M3 (absent on older thread history); the UI reads `stored` and `note`. */
  reason?: "stored" | "not_said" | "full" | "invalid" | "unavailable";
}

/** `GET/DELETE /worlds/{id}/memory`. */
export interface MemoryPayload {
  preferences: Record<string, string | string[]>;
  count: number;
  cap: number;
  short_term: { threads: number | null; checkpoint_file: string | null };
}

/** The router's pick for one chat turn (R6.5, api/sagaloom/router.py). */
export type Mode = "brainstorm" | "query" | "edit";

/** The note an import thread starts with (api/sagaloom/web/imports.py). */
export interface ImportNote {
  /** "wiki" for a fan-wiki import; a note from before wiki imports has no kind and counts as text. */
  kind?: "wiki" | "text";
  /** The filename or "paste"; the wiki's host for a wiki import. */
  source: string;
  /** The wiki's licence as read from it, kept with the import (wiki imports only). */
  licence?: { text: string | null; url: string | null; nc: boolean } | null;
  /** Each proposal's first line of imported text, keyed by proposal_id. */
  first_lines: Record<string, string>;
  /** `paste` is true where pasting the page's text instead can help. */
  skipped: { title: string; reason: string; paste?: boolean }[];
}

export interface ChatMessage {
  /** "user", "assistant", "tool", "review" (a decision note), "import" (an import's note), "memory" (the remember node's results) or "guard" (the input guard's notice
   * shown in place of a blocked message, R13.1). */
  role: string;
  content: string;
  name?: string;
  /** On a "memory" message: what `remember` did with each preference (R10.2). */
  memory?: MemoryResult[];
  /** On a "user" message: the mode the router picked for that turn. */
  mode?: Mode;
  /** On an "import" message: the import's source, first lines and left-out candidates. */
  import?: ImportNote;
  tool_calls?: { id: string | null; name: string; args: Record<string, unknown> }[];
}

export interface PendingInterrupt {
  proposals: Proposal[];
  /** Keyed by proposal_id (graph/nodes.py approval gate). */
  checks: Record<string, CheckResult>;
  error?: string;
}

export interface ThreadState {
  thread_id: string;
  world_id: string;
  messages: ChatMessage[];
  pending_interrupt: PendingInterrupt | null;
  usage: Usage;
  kind: "chat" | "import";
  title: string | null;
}

export interface ThreadSummary {
  thread_id: string;
  world_id: string;
  pending: number;
  created_at: string;
  kind: "chat" | "import";
  title: string | null;
  badge: Badge | null;
  approved: number;
  rejected: number;
  running: boolean;
}

// SSE events (R19.2), mirroring api/sagaloom/web/sse.py. llm_request / llm_response payloads
// come from the prompt-capture handler (Task 11/12) and are kept loose.
export type SseEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; args: Record<string, unknown> } }
  | { event: "tool_result"; data: { name: string; summary: string; memory?: MemoryResult[]; candidates?: number; skipped?: number } }
  | { event: "node"; data: { name: string; phase: "start" | "end"; ms?: number } }
  | { event: "llm_request"; data: Record<string, unknown> }
  | { event: "llm_response"; data: Record<string, unknown> }
  | { event: "interrupt"; data: PendingInterrupt }
  | { event: "usage"; data: { turn: Usage; total: Usage } }
  | { event: "done"; data: { thread_id?: string } }
  | { event: "error"; data: { message: string; retryable: boolean } };

// ---------- Studio and prompt capture (Task 12) ----------

export interface FeatureCardData {
  id: string;
  title: string;
  brief_ref: string;
  req_ids: string[];
  status: "live" | "configured" | "off";
  detail: string;
  try_href: string | null;
}

export interface ProviderModel {
  id: string;
  role: string;
  price_in: number | null;
  price_out: number | null;
}

export interface ProviderStatus {
  name: string;
  key_set: boolean;
  role: string;
  models: ProviderModel[];
  notice: string | null;
}

export interface ModelUsage {
  role?: string | null;
  model: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface StudioData {
  features: FeatureCardData[];
  providers: ProviderStatus[];
  usage: Usage & { by_model: ModelUsage[] };
  mermaid: string;
}

export type ModelRole = "agent" | "judge" | "extractor" | "guard";

export interface AllowedModel {
  id: string;
  price_in: number;
  price_out: number;
}

export interface ModelsPayload {
  mapping: Record<ModelRole, string>;
  allowed: AllowedModel[];
}

export interface PromptMessage {
  role: string;
  content: unknown;
  name?: string;
  tool_calls?: { id: string | null; name: string; args: Record<string, unknown> }[];
}

export interface LlmResponse {
  content: string;
  tool_calls: { id: string | null; name: string; args: Record<string, unknown> }[];
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
}

/** One prompt-log record (api/sagaloom/promptlog.py). The API types `request` and `response` as plain dicts, so their shape is narrowed here. */
export type PromptRecord = Omit<Schemas["PromptRecord"], "params" | "request" | "response"> & {
  params: Record<string, unknown>;
  request: { messages: PromptMessage[]; tools: unknown[] };
  response: LlmResponse | null;
};

// ---------- Developer settings and the input guard (R12.4, R13.1) ----------

export interface DevSettings {
  agent_temperature: number;
  agent_max_tokens: number | null;
  agent_system_prompt: string | null;
  guard_enabled: boolean;
  /** null means every tool; the core tools are on whatever this lists. */
  enabled_tools: string[] | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  core: boolean;
  enabled: boolean;
}

export interface SettingsPayload {
  settings: DevSettings;
  defaults: { agent_system_prompt: string };
  guard_policy: string;
}

/** A partial update: an explicit null clears max tokens or the prompt. */
export type SettingsPatch = Partial<DevSettings> & { reset_system_prompt?: boolean };

export interface GuardLogRow {
  thread_id: string;
  started_at: string;
  model: string;
  /** `error`: the guard call itself failed (the message was blocked); `unknown`: a reply that did not parse. */
  verdict: "safe" | "unsafe" | "injection" | "unknown" | "error";
  reason: string;
}

/** GET /api/threads/{id}/runs/last: the nodes the newest run went through. */
export interface LastRun {
  thread_id: string;
  nodes: string[];
  paused: boolean;
}
