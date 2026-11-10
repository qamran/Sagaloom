"use client";

import { useMemo, useState } from "react";
import { MASKED_LINE, UNTRUSTED, argsHoldSecret, maskPrompt, responseHoldsSecret } from "@/lib/maskSecrets";
import { useShowSecrets } from "@/lib/secrets";
import type { LlmCall, NodeStep, TurnView } from "@/lib/turns";
import type { PromptMessage } from "@/lib/types";

const LABEL = "text-[11px] uppercase tracking-[0.9px] text-muted-foreground";

const MASKED_RESPONSE = "Hidden: this call saw secret facts. Choose Show secrets to read it.";

/** A tool call as shown: its args become the mask line while hidden if they propose a secret. */
const callText = (name: string, args: unknown, hidden: boolean) =>
  `${name}(${hidden && argsHoldSecret(args) ? MASKED_LINE : JSON.stringify(args)})`;

const n = (v: number) => v.toLocaleString("en-US");
const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
const usd = (v: number) => `$${v.toFixed(4)}`;

function textOf(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((b) => (b && typeof b === "object" && "text" in b ? String((b as { text: unknown }).text) : JSON.stringify(b))).join("");
  }
  return content == null ? "" : JSON.stringify(content);
}

/** Message text with each `<untrusted_data …>…</untrusted_data>` block set apart (R13.2). */
function Content({ text }: { text: string }) {
  const parts = text.split(UNTRUSTED);
  return (
    <div className="whitespace-pre-wrap text-prose-muted">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <div
            key={i}
            data-testid="untrusted"
            className="mt-1 rounded-md border border-conflict-line bg-[#2A2418] px-2 py-1.5 text-conflict-text-2"
          >
            {p}
          </div>
        ) : (
          p && <span key={i}>{p}</span>
        ),
      )}
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  agent: "Agent",
  judge: "Contradiction judge",
  extractor: "Fact extractor",
  guard: "Input guard",
  router: "Router",
};
const ROLE_COLOR: Record<string, string> = { system: "text-myth", user: "text-place", assistant: "text-rule" };

/** One call's message texts as shown, and how many lines and tool calls were masked while hidden. */
function useShownTexts(call: LlmCall, hidden: boolean): { texts: string[]; masked: number } {
  return useMemo(() => {
    const raw = call.messages.map((m) => textOf(m.content));
    if (!hidden) return { texts: raw, masked: 0 };
    const out = raw.map(maskPrompt);
    const calls = call.messages.flatMap((m) => m.tool_calls ?? []).filter((c) => argsHoldSecret(c.args)).length;
    return { texts: out.map((o) => o.text), masked: out.reduce((a, o) => a + o.masked, calls) };
  }, [call.messages, hidden]);
}

function Messages({ call, texts, hidden }: { call: LlmCall; texts: string[]; hidden: boolean }) {
  // System first; the rest keep the order they were sent in.
  const indexed = call.messages.map((m, i): [PromptMessage, string] => [m, texts[i]]);
  const ordered = [
    ...indexed.filter(([m]) => m.role === "system"),
    ...indexed.filter(([m]) => m.role !== "system"),
  ];
  return (
    <section aria-label="Request" className="flex flex-col gap-2 bg-well px-3 py-2.5 font-mono text-[11.5px] leading-[1.55]">
      {ordered.map(([m, text], i) => (
        <div key={i}>
          <span data-testid="message-role" className={ROLE_COLOR[m.role] ?? "text-foreground"}>
            {m.role}
          </span>
          {m.name && <span className="text-muted-foreground"> · {m.name}</span>}
          <Content text={text} />
          {m.tool_calls?.map((c, j) => (
            <div key={j} className="text-place">
              {callText(c.name, c.args, hidden)}
            </div>
          ))}
        </div>
      ))}
      {call.tools.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted-foreground">
            {call.tools.length} tool schemas bound
          </summary>
          <pre className="m-0 mt-1 overflow-auto whitespace-pre-wrap text-prose-muted">
            {JSON.stringify(call.tools, null, 2)}
          </pre>
        </details>
      )}
    </section>
  );
}

/** The Response tab. It masks secret tool-call args itself while hidden, so it is safe without the
 * veil `CallCard` puts in front of it. */
export function Response({ call, hidden }: { call: LlmCall; hidden: boolean }) {
  const r = call.response;
  if (!r) return <p className="m-0 bg-well px-3 py-2.5 text-xs text-muted-foreground">No response recorded yet.</p>;
  return (
    <section aria-label="Response" className="flex flex-col gap-2 bg-well px-3 py-2.5 font-mono text-[11.5px] leading-[1.55]">
      {r.content ? (
        <div className="whitespace-pre-wrap text-prose-muted">{r.content}</div>
      ) : (
        <div className="text-muted-foreground">(no text)</div>
      )}
      {r.tool_calls.map((c, i) => (
        <div key={i} className="text-place">
          {callText(c.name, c.args, hidden)}
        </div>
      ))}
    </section>
  );
}

const requestJson = (call: LlmCall) => ({
  provider: call.provider,
  model: call.model,
  params: call.params,
  request: { messages: call.messages, tools: call.tools },
});

function MaskedResponse() {
  return (
    <section aria-label="Response" className="bg-well px-3 py-2.5 text-xs text-muted-foreground">
      {MASKED_RESPONSE}
    </section>
  );
}

function CallCard({
  call,
  index,
  defaultOpen,
  hidden,
}: {
  call: LlmCall;
  index: number;
  defaultOpen: boolean;
  /** Whether secrets are hidden: the request's secret lines are masked, the record is not. */
  hidden: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const { texts, masked } = useShownTexts(call, hidden);
  // The judge's reply has no markers, so a call that saw a secret hides its whole response; so does
  // a reply that itself carries a secret status (a proposal's args, structured output).
  const veiled = hidden && (masked > 0 || responseHoldsSecret(call.response));
  const [tab, setTab] = useState<"Request" | "Response" | "Raw JSON">("Request");
  const [copyError, setCopyError] = useState(false);
  const r = call.response;
  const role = (call.role && ROLE_LABEL[call.role]) || (call.tools.length > 0 ? "Agent" : "Structured call");
  const params = Object.entries(call.params)
    .filter(([k]) => ["temperature", "max_tokens", "reasoning_effort"].includes(k))
    .map(([k, v]) => `${k} ${String(v)}`);

  async function copy() {
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(JSON.stringify(requestJson(call), null, 2));
    } catch {
      setCopyError(true);
    }
  }

  return (
    <div className={`overflow-hidden rounded-[10px] border ${open ? "border-violet-line-strong" : "border-border"}`}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={`flex w-full flex-wrap items-center gap-x-2.5 gap-y-1 px-3 py-2 text-left text-xs ${open ? "bg-[#1C1A28]" : ""}`}
      >
        <span className="text-muted-foreground">{index + 1}</span>
        <span className="font-semibold">{role}</span>
        <span className="font-mono">{call.model}</span>
        <span className="ml-auto text-muted-foreground">
          {r
            ? `${n(r.prompt_tokens)} → ${n(r.completion_tokens)} tok · ${usd(r.cost_usd)} · ${secs(r.latency_ms)}`
            : "running…"}{" "}
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2 text-xs text-muted-foreground">
            <span>
              provider {call.provider}
              {params.length > 0 && ` · ${params.join(" · ")}`}
              {call.tools.length === 0 && " · no tools bound"}
            </span>
            <button
              type="button"
              onClick={() => void copy()}
              className="ml-auto min-h-8 rounded-lg border border-border-strong px-2.5 text-xs text-foreground"
            >
              Copy as JSON
            </button>
          </div>
          {copyError && (
            <p role="alert" className="m-0 border-b border-border px-3 py-1.5 text-xs text-conflict">
              Could not copy. Select the Raw JSON tab and copy it by hand.
            </p>
          )}
          <div className="flex border-b border-border text-xs">
            {(["Request", "Response", "Raw JSON"] as const).map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={tab === t}
                onClick={() => setTab(t)}
                className={`min-h-9 px-3 ${
                  tab === t ? "border-b-2 border-myth font-semibold text-foreground" : "text-muted-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          {tab === "Request" && <Messages call={call} texts={texts} hidden={hidden} />}
          {tab === "Response" && (veiled ? <MaskedResponse /> : <Response call={call} hidden={hidden} />)}
          {tab === "Raw JSON" && veiled && (
            <pre data-testid="raw-json" className="m-0 bg-well px-3 py-2.5 text-xs text-muted-foreground">
              {MASKED_RESPONSE}
            </pre>
          )}
          {tab === "Raw JSON" && !veiled && (
            <pre
              data-testid="raw-json"
              className="m-0 max-h-[360px] overflow-auto whitespace-pre-wrap bg-well px-3 py-2.5 font-mono text-[11px] text-prose-muted"
            >
              {JSON.stringify({ ...requestJson(call), response: call.response }, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}

function PathStep({ node }: { node: NodeStep }) {
  const paused = node.phase === "paused";
  return (
    <span
      className={`rounded-md px-[7px] py-0.5 ${
        paused ? "border-2 border-conflict" : "border border-accent"
      }`}
    >
      {node.name}{" "}
      <span className={paused ? "text-conflict-text-2" : "text-muted-foreground"}>
        {paused ? "paused" : node.ms != null ? secs(node.ms) : "…"}
      </span>
    </span>
  );
}

/** The Under the hood drawer (R20.3): graph path, tool calls and every prompt sent to OpenRouter
 * for one turn. API keys never reach this data: the prompt log is redacted on the server.
 * Secrets are masked on screen until `worldId`'s Show secrets is on; Copy stays verbatim. */
export function UnderTheHood({
  turn,
  onClose,
  threadId,
  worldId,
}: {
  turn: TurnView;
  onClose: () => void;
  threadId?: string;
  /** The world the turn's content belongs to (the thread's or import's), not the active one. */
  worldId?: string;
}) {
  const [copyError, setCopyError] = useState(false);
  const [showSecrets, setShowSecrets] = useShowSecrets(worldId);
  const totals = turn.calls.reduce(
    (a, c) => ({ cost: a.cost + (c.response?.cost_usd ?? 0), ms: a.ms + (c.response?.latency_ms ?? 0) }),
    { cost: 0, ms: 0 },
  );

  async function copyTurn() {
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ nodes: turn.nodes, tools: turn.tools, calls: turn.calls }, null, 2),
      );
    } catch {
      setCopyError(true);
    }
  }

  return (
    <aside
      aria-label="Under the hood"
      className="flex w-full flex-col border-t border-violet-line bg-well-2 md:max-w-[600px] md:flex-[1_1_560px] md:border-t-0 md:border-l"
    >
      <div className="flex flex-wrap items-center gap-2.5 border-b border-border px-[18px] py-3.5">
        <h2 className="m-0 font-heading text-xl font-semibold">Under the hood</h2>
        <span className="text-xs text-muted-foreground">
          {turn.label} · {turn.calls.length} model {turn.calls.length === 1 ? "call" : "calls"} · {usd(totals.cost)} ·{" "}
          {secs(totals.ms)}
        </span>
        <button
          type="button"
          aria-pressed={showSecrets}
          onClick={() => setShowSecrets(!showSecrets)}
          className={`ml-auto min-h-8 rounded-lg border px-2.5 text-xs ${
            showSecrets ? "border-conflict text-conflict" : "border-border-strong text-muted-foreground"
          }`}
        >
          Show secrets
        </button>
        <button
          type="button"
          onClick={() => void copyTurn()}
          className="min-h-8 rounded-lg border border-border-strong px-2.5 text-xs text-foreground"
        >
          Copy turn as JSON
        </button>
        <button
          type="button"
          aria-label="Close drawer"
          onClick={onClose}
          className="size-8 text-lg text-muted-foreground"
        >
          ×
        </button>
      </div>
      <div className="flex flex-col gap-3.5 px-[18px] py-3.5 text-[13px]">
        {copyError && (
          <p role="alert" className="m-0 text-xs text-conflict">
            Could not copy to the clipboard.
          </p>
        )}
        <div>
          <div className={`${LABEL} mb-1.5`}>Graph path</div>
          {turn.nodes.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs">
              {turn.nodes.map((node, i) => (
                <span key={i} className="flex items-center gap-1.5">
                  {i > 0 && (
                    <span aria-hidden="true" className="text-accent">
                      →
                    </span>
                  )}
                  <PathStep node={node} />
                </span>
              ))}
            </div>
          ) : (
            <p className="m-0 text-xs text-muted-foreground">
              Only the prompt log is kept after a refresh, so the graph path is not available for this turn.
            </p>
          )}
          {threadId && (
            <a
              href={`/studio?thread=${encodeURIComponent(threadId)}#agent-graph`}
              className="mt-2 inline-block text-xs text-accent underline"
            >
              See it on the agent graph
            </a>
          )}
        </div>
        {turn.nodes.length > 0 && (
          <div>
            <div className={`${LABEL} mb-1.5`}>Tool calls</div>
            {turn.tools.length === 0 ? (
              <p className="m-0 text-xs text-muted-foreground">No tools were called.</p>
            ) : (
              <div className="flex flex-col gap-1 rounded-lg border border-border bg-well px-2.5 py-2 font-mono text-xs">
                {turn.tools.map((t, i) => {
                  const masked = !showSecrets && argsHoldSecret(t.args);
                  return masked ? (
                    <div key={i}>
                      <span className="text-place">{callText(t.name, t.args, true)}</span>{" "}
                      {t.summary !== null && <span className="text-muted-foreground">→ {MASKED_LINE}</span>}
                    </div>
                  ) : (
                    <div key={i}>
                      <span className="text-place">{t.name}</span>({JSON.stringify(t.args)}){" "}
                      {t.summary !== null && <span className="text-muted-foreground">→ {t.summary}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
        <div className="flex flex-col gap-2">
          <div className={LABEL}>Prompts sent to OpenRouter</div>
          <p className="m-0 text-xs text-muted-foreground">
            Prompts are recorded exactly as sent; secret facts are hidden on screen until you choose Show. Copy as JSON
            copies the record as sent.
          </p>
          {turn.calls.length === 0 && (
            <p className="m-0 text-xs text-muted-foreground">No model calls in this turn yet.</p>
          )}
          {turn.calls.map((c, i) => (
            <CallCard key={c.id} call={c} index={i} defaultOpen={i === 0} hidden={!showSecrets} />
          ))}
        </div>
        <p className="m-0 text-[11px] text-muted-foreground">
          API keys and auth headers are never recorded. Same data as the LangSmith trace for this thread.
        </p>
      </div>
    </aside>
  );
}
