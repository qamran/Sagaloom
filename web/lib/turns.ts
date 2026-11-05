import type { TurnEvents } from "./useAgentStream";
import type { LlmResponse, Mode, PromptMessage, PromptRecord, SseEvent } from "./types";

/** One model call as the drawer shows it: the request as sent and, once it ends, the response. */
export interface LlmCall {
  id: string;
  provider: string;
  model: string;
  role?: string | null;
  params: Record<string, unknown>;
  messages: PromptMessage[];
  tools: unknown[];
  response: LlmResponse | null;
}

export interface NodeStep {
  name: string;
  /** Milliseconds once the node finished; null while it runs or when it paused. */
  ms: number | null;
  phase: "running" | "done" | "paused";
}

export interface ToolStep {
  name: string;
  args: Record<string, unknown>;
  summary: string | null;
}

/** What `<UnderTheHood>` renders for one turn. `nodes` and `tools` are empty for a turn reloaded
 * from history: only the prompt log is stored, not the stream. */
export interface TurnView {
  key: string;
  label: string;
  nodes: NodeStep[];
  tools: ToolStep[];
  calls: LlmCall[];
}

const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);
const list = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

export function callFromRecord(r: PromptRecord): LlmCall {
  return {
    id: r.id,
    provider: r.provider,
    model: r.model,
    role: r.role ?? null,
    params: r.params ?? {},
    messages: r.request?.messages ?? [],
    tools: r.request?.tools ?? [],
    response: r.response,
  };
}

const MODES: readonly Mode[] = ["brainstorm", "query", "edit"];

/** The mode in a router response (api/sagaloom/router.py RouteDecision): the content as JSON, else
 * the first tool call's args. Anything else (prose, an unknown mode, no response) is null. */
export function parseRouterMode(response: LlmResponse | null): Mode | null {
  if (!response) return null;
  const candidates: unknown[] = [];
  if (typeof response.content === "string" && response.content.trim()) {
    try {
      candidates.push(JSON.parse(response.content));
    } catch {
      /* not JSON */
    }
  }
  const first = Array.isArray(response.tool_calls) ? response.tool_calls[0] : undefined;
  if (first && typeof first === "object") candidates.push(first.args);
  for (const c of candidates) {
    const mode = c && typeof c === "object" ? (c as { mode?: unknown }).mode : undefined;
    if (MODES.includes(mode as Mode)) return mode as Mode;
  }
  return null;
}

/** Builds the turn view from the SSE events collected for one turn. */
export function viewFromEvents(t: TurnEvents): TurnView {
  const nodes: NodeStep[] = [];
  const tools: ToolStep[] = [];
  const calls: LlmCall[] = [];
  for (const ev of t.events as SseEvent[]) {
    switch (ev.event) {
      case "node": {
        if (ev.data.phase === "start") nodes.push({ name: ev.data.name, ms: null, phase: "running" });
        else {
          const open = [...nodes].reverse().find((n) => n.name === ev.data.name && n.phase === "running");
          if (open) {
            open.ms = ev.data.ms ?? null;
            open.phase = "done";
          } else nodes.push({ name: ev.data.name, ms: ev.data.ms ?? null, phase: "done" });
        }
        break;
      }
      case "tool_call":
        tools.push({ name: ev.data.name, args: ev.data.args, summary: null });
        break;
      case "tool_result": {
        const open = tools.find((x) => x.name === ev.data.name && x.summary === null);
        if (open) open.summary = ev.data.summary;
        else tools.push({ name: ev.data.name, args: {}, summary: ev.data.summary });
        break;
      }
      case "llm_request": {
        const d = ev.data;
        calls.push({
          id: str(d.id, `call-${calls.length}`),
          provider: str(d.provider, "openrouter"),
          model: str(d.model, "unknown"),
          role: typeof d.role === "string" ? d.role : null,
          params: (d.params as Record<string, unknown>) ?? {},
          messages: list<PromptMessage>(d.messages),
          tools: list<unknown>(d.tools),
          response: null,
        });
        break;
      }
      case "llm_response": {
        const call = calls.find((c) => c.id === ev.data.id);
        if (call) call.response = ev.data as unknown as LlmResponse;
        break;
      }
      case "interrupt": {
        // The run paused at the approval gate: it has no end event.
        const gate = [...nodes].reverse().find((n) => n.name === "approval_gate");
        if (gate) gate.phase = "paused";
        else nodes.push({ name: "approval_gate", ms: null, phase: "paused" });
        break;
      }
    }
  }
  return { key: `live-${t.turn}`, label: "", nodes, tools, calls };
}

/** Groups prompt-log records by their turn id (`run_id`), in the order the turns started. */
export function groupRecords(records: PromptRecord[]): { runId: string; calls: LlmCall[] }[] {
  const groups = new Map<string, LlmCall[]>();
  for (const r of records) {
    const g = groups.get(r.run_id) ?? [];
    g.push(callFromRecord(r));
    groups.set(r.run_id, g);
  }
  return [...groups].map(([runId, calls]) => ({ runId, calls }));
}

/**
 * Every turn for the drawer: turns reloaded from the log first, then this page's live turns. A log
 * group whose call ids appear in a live turn is that turn (the live view also has nodes and tools),
 * so it is not listed twice. Labels count from 1.
 */
export function buildTurnViews(live: TurnEvents[], records: PromptRecord[]): TurnView[] {
  const liveViews = live.map(viewFromEvents);
  const liveIds = new Set(liveViews.flatMap((v) => v.calls.map((c) => c.id)));
  const history: TurnView[] = groupRecords(records)
    .filter((g) => !g.calls.some((c) => liveIds.has(c.id)))
    .map((g) => ({ key: `run-${g.runId}`, label: "", nodes: [], tools: [], calls: g.calls }));
  return [...history, ...liveViews].map((v, i) => ({ ...v, label: `Turn ${i + 1}` }));
}
