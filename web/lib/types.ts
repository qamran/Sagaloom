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
  edited: EntryDraft | null;
  told_by: string | null;
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
  checks: CheckResult[];
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

// SSE events (R19.2). Payloads of events owned by Task 11 are kept loose on purpose.
export type SseEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { id?: string | null; name: string; args: Record<string, unknown> } }
  | { event: "tool_result"; data: { id?: string | null; name: string; content: string } }
  | { event: "node"; data: { name: string; phase?: string; ms?: number } }
  | { event: "llm_request"; data: Record<string, unknown> }
  | { event: "llm_response"; data: Record<string, unknown> }
  | { event: "interrupt"; data: PendingInterrupt }
  | { event: "usage"; data: { turn?: Usage; thread?: Usage } & Partial<Usage> }
  | { event: "done"; data: Record<string, unknown> }
  | { event: "error"; data: { message: string } };
