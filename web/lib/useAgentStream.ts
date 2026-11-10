"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getThread } from "./api";
import { detailOf, readEvents } from "./readSse";
import { markTour } from "./tour";
import { parseRouterMode } from "./turns";
import type { ChatMessage, Decision, ImportNote, LlmResponse, Mode, PendingInterrupt, SseEvent, ThreadState, Usage } from "./types";

export type StreamStatus = "idle" | "streaming" | "reconnecting" | "error";

/**
 * Everything the API streamed in one turn except tokens and the terminal `done`/`error`:
 * `node`, `llm_request`, `llm_response`, `tool_call`, `tool_result`, `interrupt` and `usage`,
 * in arrival order. Kept for the Under the hood drawer (Task 12). `turn` counts from 1 per page
 * load; `kind` says whether the turn was a chat message or an approval decision.
 */
export interface TurnEvents {
  turn: number;
  kind: "message" | "decision";
  events: SseEvent[];
}

export interface AgentStream {
  messages: ChatMessage[];
  /** True while a turn's stream is open. */
  streaming: boolean;
  pending: PendingInterrupt | null;
  /** Thread totals (from `GET /threads/{id}` or the last `usage` event). */
  usage: Usage | null;
  status: StreamStatus;
  error: string | null;
  /** True once the first `getThread` has answered. */
  loaded: boolean;
  /** The world this thread belongs to, once `getThread` has answered. */
  worldId: string | null;
  /** What started the thread, and its title, once `getThread` has answered. */
  kind: "chat" | "import";
  title: string | null;
  /** On an import thread: where the text came from, each proposal's first line, what was left out. */
  importNote: ImportNote | null;
  /** Decisions picked so far for the pending card(s), keyed by proposal_id. */
  chosen: Record<string, Decision>;
  /** The set just sent for decision, with its choices, kept (while `pending` is null) until the next interrupt. */
  sent: { pending: PendingInterrupt; chosen: Record<string, Decision> } | null;
  turnEvents: TurnEvents[];
  send: (content: string) => Promise<void>;
  /** Sends decisions now. They must name exactly the pending proposal ids. */
  decide: (decisions: Decision[]) => Promise<void>;
  /** Records one card's decision; submits all of them once every pending proposal has one (unless `autoSubmit` is off). */
  choose: (decision: Decision) => Promise<void>;
  /** Records several decisions at once (the bulk buttons); same submit rule as `choose`. */
  chooseMany: (decisions: Decision[]) => Promise<void>;
  /** Takes back one card's decision before the set is submitted. */
  unchoose: (proposalId: string) => void;
}

const PENDING_FIRST = "Decide on the pending change first";
const BUSY = "A reply is still running. Wait for it to finish.";
const UNREACHABLE = "Could not reach Sagaloom. Please try again.";
const LOST = "Lost the connection and could not reload this conversation. Refresh the page.";

const hasConflict = (p: PendingInterrupt) =>
  Object.values(p.checks).some((c) => c.flags.some((f) => f.kind === "conflict"));

/** Who a streamed token belongs to: the input guard's notice or the assistant's reply. */
type TokenRole = "assistant" | "guard";

/**
 * Appends a streamed event to the message list in the same shape `GET /threads/{id}` returns.
 * `tokenRole` says whose text a `token` is; a guard notice never merges into an assistant reply.
 */
function applyToMessages(msgs: ChatMessage[], ev: SseEvent, tokenRole: TokenRole = "assistant"): ChatMessage[] {
  const last = msgs[msgs.length - 1];
  const openAssistant = last?.role === "assistant" && !last.tool_calls;
  switch (ev.event) {
    case "token":
      if (tokenRole === "guard") {
        if (last?.role === "guard") return [...msgs.slice(0, -1), { ...last, content: last.content + ev.data.text }];
        return [...msgs, { role: "guard", content: ev.data.text }];
      }
      if (openAssistant) return [...msgs.slice(0, -1), { ...last, content: last.content + ev.data.text }];
      return [...msgs, { role: "assistant", content: ev.data.text }];
    case "tool_call": {
      const call = { id: null, name: ev.data.name, args: ev.data.args };
      // Calls stream right after the AI message's text (or after its sibling calls).
      if (last?.role === "assistant") {
        return [...msgs.slice(0, -1), { ...last, tool_calls: [...(last.tool_calls ?? []), call] }];
      }
      return [...msgs, { role: "assistant", content: "", tool_calls: [call] }];
    }
    case "tool_result": {
      // Tool output can quote secret facts, so only the tool name is kept for display.
      const tool: ChatMessage = { role: "tool", name: ev.data.name, content: "" };
      // `remember` also yields a memory message; its chips read the items, never the summary.
      if (ev.data.name === "remember" && ev.data.memory?.length) {
        return [...msgs, tool, { role: "memory", content: ev.data.summary, memory: ev.data.memory }];
      }
      return [...msgs, tool];
    }
    default:
      return msgs;
  }
}

/** Puts the router's mode on the author's latest message (the one this turn sent). */
function withMode(msgs: ChatMessage[], mode: Mode): ChatMessage[] {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "user") return [...msgs.slice(0, i), { ...msgs[i], mode }, ...msgs.slice(i + 1)];
  }
  return msgs;
}

export function useAgentStream(threadId: string, opts: { autoSubmit?: boolean } = {}): AgentStream {
  const autoSubmit = opts.autoSubmit ?? true;
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPendingState] = useState<PendingInterrupt | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [threadWorld, setThreadWorld] = useState<string | null>(null);
  const [threadKind, setThreadKind] = useState<"chat" | "import">("chat");
  const [threadTitle, setThreadTitle] = useState<string | null>(null);
  const [chosen, setChosenState] = useState<Record<string, Decision>>({});
  const [sent, setSent] = useState<AgentStream["sent"]>(null);
  const [turnEvents, setTurnEvents] = useState<TurnEvents[]>([]);

  // Mirrors of state that callbacks read synchronously.
  const pendingRef = useRef<PendingInterrupt | null>(null);
  const chosenRef = useRef<Record<string, Decision>>({});
  const busyRef = useRef(false);
  const turnRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const aliveRef = useRef(true);

  const setPending = useCallback((p: PendingInterrupt | null) => {
    pendingRef.current = p;
    setPendingState(p);
    if (p) setSent(null);
    // A new interrupt (also after an edit re-check, same proposal ids) starts a fresh choice.
    chosenRef.current = {};
    setChosenState({});
  }, []);

  const setChosen = useCallback((c: Record<string, Decision>) => {
    chosenRef.current = c;
    setChosenState(c);
  }, []);

  const applyThread = useCallback(
    (t: ThreadState) => {
      setMessages(t.messages);
      setThreadWorld(t.world_id);
      setThreadKind(t.kind ?? "chat");
      setThreadTitle(t.title ?? null);
      setPending(t.pending_interrupt);
      setUsage(t.usage);
    },
    [setPending],
  );

  const restore = useCallback(async () => {
    const t = await getThread(threadId);
    if (!aliveRef.current) return;
    applyThread(t);
  }, [threadId, applyThread]);

  useEffect(() => {
    aliveRef.current = true;
    let cancelled = false;
    getThread(threadId).then(
      (t) => {
        if (cancelled) return;
        applyThread(t);
        setLoaded(true);
      },
      () => {
        if (cancelled) return;
        setStatus("error");
        setError("Could not load this conversation.");
        setLoaded(true);
      },
    );
    return () => {
      cancelled = true;
      aliveRef.current = false;
      abortRef.current?.abort();
    };
  }, [threadId, applyThread]);

  const run = useCallback(
    async (path: "messages" | "decisions", body: unknown, kind: TurnEvents["kind"], onOk: () => void) => {
      if (busyRef.current) {
        setError(BUSY);
        return;
      }
      busyRef.current = true;
      const turn = (turnRef.current += 1);
      const record = (ev: SseEvent) =>
        setTurnEvents((all) => all.map((t) => (t.turn === turn ? { ...t, events: [...t.events, ev] } : t)));
      setTurnEvents((all) => [...all, { turn, kind, events: [] }]);
      setStatus("streaming");
      setError(null);
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      let ended: "done" | "error" | null = null;
      const reconnect = async () => {
        setStatus("reconnecting");
        try {
          await restore();
          setStatus("idle");
        } catch {
          setStatus("error");
          setError(LOST);
        }
      };

      try {
        let res: Response;
        try {
          res = await fetch(`/api/proxy/threads/${encodeURIComponent(threadId)}/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify(body),
            signal: ctrl.signal,
          });
        } catch {
          if (!ctrl.signal.aborted) await reconnect();
          return;
        }

        if (!res.ok || !res.body) {
          const detail = await detailOf(res);
          setStatus("error");
          if (res.status === 409 && detail === "turn in progress") {
            setError(BUSY);
            return;
          }
          if (res.status === 409 && detail === "approval pending") setError(PENDING_FIRST);
          else if (res.status === 409 && detail === "no pending approval") setError("This change was already decided.");
          else if (res.status === 429) setError("Too many requests. Wait a moment and try again.");
          else if (res.status === 413) setError("That message is too large.");
          else if (res.status === 422) setError(detail || "That decision was not accepted.");
          else setError(UNREACHABLE);
          // The card or the conversation may be stale: re-read the thread.
          if (res.status === 409 || res.status === 422) await restore().catch(() => undefined);
          return;
        }

        onOk();
        // The guard's notice is streamed as tokens while the guard is the last node to have
        // started; its `node end` may arrive before or after the token, so the start decides.
        let lastStarted: string | null = null;
        // Ids of this turn's router calls: their response carries the mode for the chip.
        const routerCalls = new Set<string>();
        ended = await readEvents(res, (ev) => {
          switch (ev.event) {
            case "done":
              break;
            case "error":
              setStatus("error");
              setError(ev.data.message);
              break;
            case "token": {
              const role: TokenRole = lastStarted === "guard" ? "guard" : "assistant";
              setMessages((m) => applyToMessages(m, ev, role));
              break;
            }
            case "tool_call":
            case "tool_result":
              setMessages((m) => applyToMessages(m, ev));
              record(ev);
              break;
            case "interrupt":
              setPending(ev.data);
              if (hasConflict(ev.data)) markTour("conflict");
              record(ev);
              break;
            case "usage":
              setUsage(ev.data.total);
              record(ev);
              break;
            case "node":
              if (ev.data.phase === "start") lastStarted = ev.data.name;
              record(ev);
              break;
            case "llm_request":
              if (ev.data.role === "router" && typeof ev.data.id === "string") routerCalls.add(ev.data.id);
              record(ev);
              break;
            case "llm_response": {
              if (typeof ev.data.id === "string" && routerCalls.has(ev.data.id)) {
                const mode = parseRouterMode(ev.data as unknown as LlmResponse);
                if (mode) setMessages((m) => withMode(m, mode));
              }
              record(ev);
              break;
            }
            default:
              record(ev);
          }
        });
        if (ctrl.signal.aborted) return;
        if (ended === null) {
          await reconnect();
        } else if (ended === "done") {
          // Commit review notes are not streamed; re-read them after a decision, and stay
          // "streaming" until they land so a page never shows a finished turn without them.
          if (kind === "decision") {
            await restore().then(
              () => setStatus("idle"),
              () => {
                setStatus("error");
                setError(LOST);
              },
            );
          } else setStatus("idle");
        } else {
          await restore().catch(() => undefined);
        }
      } finally {
        busyRef.current = false;
        if (abortRef.current === ctrl) abortRef.current = null;
        void qc.invalidateQueries({ queryKey: ["thread", threadId] });
        void qc.invalidateQueries({ queryKey: ["llm-log", threadId] });
        if (kind === "decision") void qc.invalidateQueries({ queryKey: ["entries"] });
        void qc.invalidateQueries({ queryKey: ["review"] });
      }
    },
    [threadId, qc, restore, setPending],
  );

  const send = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text) return;
      if (pendingRef.current) {
        setError(PENDING_FIRST);
        return;
      }
      await run("messages", { content: text }, "message", () => {
        markTour("chatted");
        setMessages((m) => [...m, { role: "user", content: text }]);
      });
    },
    [run],
  );

  const decide = useCallback(
    async (decisions: Decision[]) => {
      const asked = pendingRef.current?.proposals.map((p) => p.proposal_id) ?? [];
      const given = decisions.map((d) => d.proposal_id);
      const exact =
        asked.length > 0 &&
        given.length === asked.length &&
        new Set(given).size === given.length &&
        given.every((id) => asked.includes(id));
      if (!exact) {
        setError("Choose an action for every pending change before submitting.");
        return;
      }
      const ordered = asked.map((id) => decisions.find((d) => d.proposal_id === id) as Decision);
      await run("decisions", { decisions: ordered }, "decision", () => {
        if (ordered.some((d) => d.action === "save_as_myth")) markTour("myth");
        if (pendingRef.current) {
          setSent({ pending: pendingRef.current, chosen: Object.fromEntries(ordered.map((d) => [d.proposal_id, d])) });
        }
        setPending(null);
      });
    },
    [run, setPending],
  );

  const chooseMany = useCallback(
    async (decisions: Decision[]) => {
      const asked = pendingRef.current?.proposals.map((p) => p.proposal_id) ?? [];
      const next = { ...chosenRef.current };
      for (const d of decisions) if (asked.includes(d.proposal_id)) next[d.proposal_id] = d;
      setChosen(next);
      if (autoSubmit && asked.length > 0 && asked.every((id) => next[id])) await decide(asked.map((id) => next[id]));
    },
    [decide, setChosen, autoSubmit],
  );

  const choose = useCallback((decision: Decision) => chooseMany([decision]), [chooseMany]);

  const unchoose = useCallback(
    (proposalId: string) => {
      const next = { ...chosenRef.current };
      delete next[proposalId];
      setChosen(next);
    },
    [setChosen],
  );

  const importNote = useMemo(() => messages.find((m) => m.role === "import")?.import ?? null, [messages]);

  return {
    messages,
    streaming: status === "streaming",
    pending,
    usage,
    worldId: threadWorld,
    kind: threadKind,
    title: threadTitle,
    importNote,
    status,
    error,
    loaded,
    chosen,
    sent,
    turnEvents,
    send,
    decide,
    choose,
    chooseMany,
    unchoose,
  };
}
