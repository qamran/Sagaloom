"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { Composer } from "@/components/Composer";
import { getEntries } from "@/lib/api";
import type { ChatMessage, PendingInterrupt } from "@/lib/types";
import { useAgentStream } from "@/lib/useAgentStream";
import { useWorld } from "@/lib/world";

const PENDING_HINT = "Decide on the pending change first";

const TOOL_LABEL: Record<string, string> = {
  search_canon: "Searched canon",
  create_or_update_entry: "Drafted a proposal",
  check_contradiction: "Checked facts",
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

function ActivityLine({ label, done, warn }: { label: string; done: boolean; warn?: boolean }) {
  return (
    <div className={warn ? "text-[#f0b98a]" : undefined}>
      <span aria-hidden="true">{warn ? "!" : done ? "✓" : "…"}</span> {label}
    </div>
  );
}

function Message({ m, done }: { m: ChatMessage; done: boolean }) {
  if (m.role === "user") {
    return (
      <div className="max-w-[80%] self-end whitespace-pre-wrap rounded-[14px_14px_4px_14px] border border-[#2e3834] bg-panel-3 px-4 py-3">
        <span className="sr-only">You: </span>
        {m.content}
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
            <ActivityLine key={`${c.name}-${i}`} label={toolLabel(c.name)} done={done} />
          ))}
        </div>
      )}
    </>
  );
}

export function ChatThread({ threadId }: { threadId: string }) {
  const s = useAgentStream(threadId);
  const { world, setThreadId } = useWorld();
  const bottom = useRef<HTMLDivElement>(null);

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

  const last = s.messages[s.messages.length - 1];
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [s.messages.length, last?.content, s.pending]);

  const pending = s.pending;
  const busy = s.status === "streaming" || s.status === "reconnecting";
  const many = (pending?.proposals.length ?? 0) > 1;
  const summary = pending ? checkSummary(pending) : null;
  const thinking = s.streaming && (!last || last.role !== "assistant" || !!last.tool_calls);

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col">
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

        {s.messages.map((m, i) => (
          <Message
            key={i}
            m={m}
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
          placeholder={`Ask about ${world?.name ?? "your world"}, add a fact, or brainstorm.`}
        />
      </div>
    </main>
  );
}
