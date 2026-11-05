"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { CourseChip } from "@/components/CourseChip";
import { RememberedChip } from "@/components/RememberedChip";
import { Composer } from "@/components/Composer";
import { UnderTheHood } from "@/components/UnderTheHood";
import { getEntries, getLlmLog, getSettings } from "@/lib/api";
import { buildTurnViews } from "@/lib/turns";
import type { ChatMessage, PendingInterrupt } from "@/lib/types";
import { useAgentStream } from "@/lib/useAgentStream";
import { useWorld } from "@/lib/world";

const PENDING_HINT = "Decide on the pending change first";

const TOOL_LABEL: Record<string, string> = {
  search_canon: "Searched canon",
  create_or_update_entry: "Drafted a proposal",
  check_contradiction: "Checked facts",
  real_world_reference: "Looking it up on Wikipedia",
};
const toolLabel = (name: string) => TOOL_LABEL[name] ?? `Used ${name.replaceAll("_", " ")}`;

/** "Checked facts · 1 conflict, 1 retcon" for the pending interrupt. */
function checkSummary(p: PendingInterrupt): { text: string; warn: boolean } {
  const checks = Object.values(p.checks);
  if (checks.some((c) => c.verdict === "failed")) return { text: "Check failed", warn: true };
  const count = (kind: string) => checks.reduce((n, c) => n + c.flags.filter((f) => f.kind === kind).length, 0);
  const parts = (
    [
      ["conflict", "conflict", "conflicts"],
      ["retcon", "retcon", "retcons"],
      ["note", "note", "notes"],
    ] as const
  )
    .map(([kind, one, many]) => [count(kind), one, many] as const)
    .filter(([n]) => n > 0)
    .map(([n, one, many]) => `${n} ${n === 1 ? one : many}`);
  const warn = checks.some((c) => c.verdict === "conflict" || c.verdict === "possible") || parts.length > 0;
  return { text: parts.length ? parts.join(", ") : "no conflicts found", warn };
}

function ActivityLine({ label, done, warn, chip }: { label: string; done: boolean; warn?: boolean; chip?: ReactNode }) {
  return (
    <div className={warn ? "text-[#f0b98a]" : undefined}>
      <span aria-hidden="true">{warn ? "!" : done ? "✓" : "…"}</span> {label}
      {chip && <> {chip}</>}
    </div>
  );
}

function Message({ m, done, worldId }: { m: ChatMessage; done: boolean; worldId?: string }) {
  if (m.role === "memory") {
    // Chips come from the items (note and value), never from the agent-facing content.
    return (
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        {(m.memory ?? []).map((r, i) => (
          <RememberedChip key={`${r.key}-${i}`} worldId={worldId} result={r} />
        ))}
        <CourseChip card="memory" label="Memory · store" />
      </div>
    );
  }
  if (m.role === "user") {
    return (
      <div className="max-w-[80%] self-end whitespace-pre-wrap rounded-[14px_14px_4px_14px] border border-[#2e3834] bg-panel-3 px-4 py-3">
        <span className="sr-only">You: </span>
        {m.content}
        {m.mode && (
          <div className="mt-1.5 flex justify-end">
            <CourseChip card="router" label={`Router · ${m.mode}`} />
          </div>
        )}
      </div>
    );
  }
  if (m.role === "review") {
    return (
      <div className="rounded-lg border border-border px-3 py-2 text-[13px] text-muted-foreground">
        {m.content}
      </div>
    );
  }
  if (m.role === "guard") {
    return (
      <div
        role="note"
        aria-label="Blocked by the input guard"
        className="max-w-[90%] rounded-lg border border-border bg-panel-2 px-3 py-2 text-[14px] text-muted-foreground"
      >
        <div className="mb-0.5 flex items-center gap-2 text-xs uppercase tracking-[1px] text-accent">
          Input guard
          <CourseChip card="security_guard" label="Guardrail" />
        </div>
        {m.content}
      </div>
    );
  }
  if (m.role !== "assistant") return null; // tool output can quote secrets: never shown
  return (
    <>
      {m.content && (
        <div className="max-w-[90%] whitespace-pre-wrap font-heading text-[16px] leading-[1.6] text-[#e3dfd5]">
          <span className="sr-only">Sagaloom: </span>
          {m.content}
        </div>
      )}
      {m.tool_calls && m.tool_calls.length > 0 && (
        <div className="flex flex-col gap-[5px] pl-0.5 text-xs text-muted-foreground">
          {m.tool_calls.map((c, i) => (
            <ActivityLine
              key={`${c.name}-${i}`}
              label={toolLabel(c.name)}
              done={done}
              chip={c.name === "search_canon" ? <CourseChip card="agentic_rag" label="Agentic RAG" /> : undefined}
            />
          ))}
        </div>
      )}
    </>
  );
}

export function ChatThread({ threadId, initialPrompt }: { threadId: string; initialPrompt?: string | null }) {
  const s = useAgentStream(threadId);
  const { world, setThreadId } = useWorld();
  const bottom = useRef<HTMLDivElement>(null);
  const [hood, setHood] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  // Whether the thread already had messages when first loaded (a restored thread, not a new one).
  const [restored, setRestored] = useState<boolean | null>(null);
  if (s.loaded && restored === null) setRestored(s.messages.length > 0);

  // The header's cost pill follows this thread.
  useEffect(() => {
    setThreadId(threadId);
    return () => setThreadId(null);
  }, [threadId, setThreadId]);

  const worldId = s.pending?.proposals[0]?.world_id ?? world?.id;
  const { data: canon } = useQuery({
    queryKey: ["entries", worldId],
    queryFn: () => getEntries(worldId as string),
    // Loaded up front so cited secrets can be identified; the card fails closed until then.
    enabled: !!worldId,
  });

  // Turns from this page load come from the stream; earlier ones are rebuilt from the prompt log.
  const { data: log } = useQuery({
    queryKey: ["llm-log", threadId],
    queryFn: () => getLlmLog(threadId),
    enabled: hood && !s.streaming,
  });
  const turns = useMemo(() => buildTurnViews(s.turnEvents, log ?? []), [s.turnEvents, log]);
  const shown = turns.find((t) => t.key === picked) ?? turns[turns.length - 1] ?? null;

  const { data: dev } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const guardOff = dev?.settings.guard_enabled === false;

  const last = s.messages[s.messages.length - 1];
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [s.messages.length, last?.content, s.pending]);

  const pending = s.pending;
  const busy = s.status === "streaming" || s.status === "reconnecting";
  const many = (pending?.proposals.length ?? 0) > 1;
  const summary = pending ? checkSummary(pending) : null;
  const thinking =
    s.streaming && (!last || (last.role !== "assistant" && last.role !== "guard") || !!last.tool_calls);

  return (
    <div className="flex min-h-0 flex-1 flex-wrap">
    <main className="flex min-h-0 min-w-0 flex-[999_1_520px] flex-col">
      {guardOff && (
        <div
          role="status"
          aria-label="Input guard status"
          className="border-b border-border bg-panel-2 px-4 py-1 text-xs text-muted-foreground md:px-7"
        >
          <a href="/studio#guardrails" className="text-conflict underline">
            Input guard off (Studio)
          </a>
        </div>
      )}
      <div className="flex items-center justify-end gap-2.5 px-4 pt-3 md:px-7">
        {hood && turns.length > 1 && (
          <>
            <label htmlFor="hood-turn" className="sr-only">
              Turn shown in Under the hood
            </label>
            <select
              id="hood-turn"
              value={shown?.key ?? ""}
              onChange={(e) => setPicked(e.target.value)}
              className="min-h-9 rounded-lg border border-border bg-panel-3 px-2 text-xs text-foreground"
            >
              {turns.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </>
        )}
        {hood && shown && turns.length === 1 && <span className="text-xs text-muted-foreground">{shown.label} selected</span>}
        <button
          type="button"
          aria-pressed={hood}
          onClick={() => setHood(!hood)}
          className={`flex min-h-9 items-center gap-2 rounded-lg border px-3 text-[13px] ${
            hood ? "border-[#5B4785] bg-[#2A2340] text-myth" : "border-border-strong text-foreground"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M8 6l-6 6 6 6M16 6l6 6-6 6" />
          </svg>
          Under the hood
        </button>
      </div>
      <div
        role="log"
        aria-label="Conversation"
        aria-busy={busy}
        className="mx-auto box-border flex w-full max-w-[860px] flex-1 flex-col gap-4 px-4 py-6 md:px-10 md:py-7"
      >
        {!s.loaded && <p className="m-0 text-muted-foreground">Loading conversation…</p>}
        {s.loaded && s.messages.length === 0 && !pending && (
          <div className="flex flex-col gap-2">
            <div className="text-xs uppercase tracking-[1px] text-accent">Chat</div>
            <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">
              Talk to {world?.name ?? "your world"}
            </h1>
            <p className="m-0 font-heading text-[17px] text-[#c9c6bd]">
              Ask a question, or propose a new fact. Every change is checked against canon and waits for your
              approval.
            </p>
          </div>
        )}

        {restored && (
          <div>
            <CourseChip card="memory" label="Memory · checkpointer" />
          </div>
        )}

        {s.messages.map((m, i) => (
          <Message
            key={i}
            m={m}
            worldId={s.worldId ?? world?.id}
            done={s.messages.slice(i + 1).some((n) => n.role === "tool" || n.role === "assistant") || !busy}
          />
        ))}

        {thinking && (
          <div className="text-xs text-muted-foreground">
            <span aria-hidden="true">…</span> Thinking
          </div>
        )}

        {pending && summary && (
          <div className="flex flex-col gap-3.5">
            <div className="flex flex-col gap-[5px] pl-0.5 text-xs text-muted-foreground">
              <ActivityLine label={`Checked facts · ${summary.text}`} done warn={summary.warn} />
            </div>
            {pending.error && (
              <p role="alert" className="m-0 text-sm text-conflict">
                {pending.error}
              </p>
            )}
            {many && (
              <p className="m-0 text-[13px] text-muted-foreground">
                {pending.proposals.length} changes to decide. Choose for each one; they are sent together.
              </p>
            )}
            {pending.proposals.map((p) => {
              const check = pending.checks[p.proposal_id];
              if (!check) return null;
              return (
                <ApprovalCard
                  key={p.proposal_id}
                  proposal={p}
                  check={check}
                  canon={canon}
                  chosen={many ? s.chosen[p.proposal_id] : undefined}
                  onUndo={() => s.unchoose(p.proposal_id)}
                  disabled={busy}
                  onDecide={(d) => void s.choose(d)}
                />
              );
            })}
          </div>
        )}

        {s.status === "reconnecting" && (
          <p role="status" className="m-0 text-sm text-muted-foreground">
            Connection lost. Reconnecting…
          </p>
        )}
        {s.error && !(pending && s.error === PENDING_HINT) && (
          <p role="alert" className="m-0 text-sm text-conflict">
            {s.error}
          </p>
        )}
        <div ref={bottom} />
      </div>

      <div className="sticky bottom-0 border-t border-border bg-background px-4 pt-3.5 pb-5 md:px-10">
        <Composer
          onSend={(text) => void s.send(text)}
          disabled={!s.loaded || busy || !!pending}
          hint={pending ? PENDING_HINT : null}
          prefill={initialPrompt}
          placeholder={`Ask about ${world?.name ?? "your world"}, add a fact, or brainstorm.`}
        />
      </div>
    </main>
    {hood &&
      (shown ? (
        <UnderTheHood turn={shown} threadId={threadId} onClose={() => setHood(false)} />
      ) : (
        <aside aria-label="Under the hood" className="w-full border-t border-[#3A3355] bg-[#14181A] p-[18px] md:max-w-[600px] md:flex-[1_1_560px] md:border-t-0 md:border-l">
          <h2 className="m-0 font-heading text-xl font-semibold">Under the hood</h2>
          <p className="text-[13px] text-muted-foreground">
            {s.loaded ? "Send a message to see the prompts behind each turn." : "Loading…"}
          </p>
        </aside>
      ))}
    </div>
  );
}
