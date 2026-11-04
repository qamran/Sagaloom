// Mirrors api/sagaloom/models.py and the JSON shapes in api/sagaloom/web/routes.py.

export type EntryType = "character" | "place" | "faction" | "item" | "rule" | "event";
export type Status = "canon" | "myth" | "rumour" | "secret";
export type Source = "user" | "official" | "reference";

export interface Fact {
  key: string;
  value: string;
  refs: string[];
  status: Status;
  told_by: string | null;
}

export interface Link {
  target_id: string;
  relation: string;
}

export interface Entry {
  id: string;
  world_id: string;
  title: string;
  type: EntryType;
  body: string;
  status: Status;
  source: Source;
  source_url: string | null;
  licence: string | null;
  trusted: boolean;
  aliases: string[];
  links: Link[]; // never rendered in M1: relations can reveal secrets
  facts: Fact[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EntryDraft {
  title: string;
  type: EntryType;
  body: string;
  status: Status;
  aliases: string[];
  facts: Fact[];
}

export interface World {
  id: string;
  name: string;
  is_demo: boolean;
  divergent: boolean;
}

export interface Proposal {
  proposal_id: string;
  action: "create" | "update" | "delete";
  world_id: string;
  entry_id: string | null;
  before: Entry | null;
  after: EntryDraft | null;
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
}

export interface EntryRef {
  id: string;
  title: string;
  type: EntryType;
}

export interface CheckResult {
  proposal_id: string;
  verdict: "none" | "possible" | "conflict" | "failed";
  flags: Flag[];
  dependents: EntryRef[];
}

export interface Decision {
  proposal_id: string;
  action: "approve" | "edit" | "reject" | "save_as_myth";
  edited?: EntryDraft | null;
  told_by?: string | null;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface ChatMessage {
  role: string;
  content: string;
  name?: string;
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
}

export interface ThreadSummary {
  thread_id: string;
  world_id: string;
  pending: number;
}

// SSE events (R19.2), mirroring api/sagaloom/web/sse.py. llm_request / llm_response payloads
// come from the prompt-capture handler (Task 11/12) and are kept loose.
export type SseEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; args: Record<string, unknown> } }
  | { event: "tool_result"; data: { name: string; summary: string } }
  | { event: "node"; data: { name: string; phase: "start" | "end"; ms?: number } }
  | { event: "llm_request"; data: Record<string, unknown> }
  | { event: "llm_response"; data: Record<string, unknown> }
  | { event: "interrupt"; data: PendingInterrupt }
  | { event: "usage"; data: { turn: Usage; total: Usage } }
  | { event: "done"; data: Record<string, never> }
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

/** One prompt-log record (api/sagaloom/promptlog.py PromptRecord). */
export interface PromptRecord {
  id: string;
  thread_id: string;
  run_id: string;
  provider: string;
  model: string;
  params: Record<string, unknown>;
  request: { messages: PromptMessage[]; tools: unknown[] };
  response: LlmResponse | null;
  started_at: string;
}
