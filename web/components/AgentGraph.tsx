"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getLastRun, getThreads } from "@/lib/api";
import { hasMessages } from "@/lib/dashboard";
import { highlightMermaid } from "@/lib/mermaid";
import { ago } from "@/lib/time";
import type { ThreadSummary } from "@/lib/types";
import { useWorld } from "@/lib/world";

/** "How many moons does Velmar have? · chat · 21 min ago": what a person recognises, not the id. */
function threadLabel(t: ThreadSummary): string {
  return [t.title ?? "Untitled chat", t.kind, ago(t.created_at)].filter(Boolean).join(" · ");
}

/** The compiled graph as a diagram, with the nodes of a thread's last run highlighted (R20.4). */
export function AgentGraph({ mermaid }: { mermaid: string }) {
  const wanted = useSearchParams().get("thread");
  const { world } = useWorld();
  const all = useQuery({ queryKey: ["threads"], queryFn: getThreads });
  // Only the world selected in the header, as on the rest of Studio, and only threads that ran:
  // an empty chat has no run to draw.
  const list = all.data?.filter((t) => t.world_id === world?.id && (t.kind !== "chat" || hasMessages(t)));
  const threads = { data: world ? list : undefined };
  const [picked, setPicked] = useState<string | null>(null);
  const ids = threads.data?.map((t) => t.thread_id) ?? [];
  const first = ids[0] ?? null;
  const pick = [picked, wanted].find((id) => id && ids.includes(id));
  // An unknown ?thread= falls back to the first thread. No last-run request until the list has loaded.
  const threadId = pick ?? (threads.data ? first : null);
  const run = useQuery({
    queryKey: ["last-run", threadId],
    queryFn: () => getLastRun(threadId as string),
    enabled: !!threadId,
    placeholderData: keepPreviousData,
  });
  const nodes = run.data?.nodes;
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!mermaid) return;
    let live = true;
    (async () => {
      try {
        const { default: m } = await import("mermaid"); // client only: Next must not load it on the server
        m.initialize({ startOnLoad: false, theme: "dark" });
        const out = await m.render(`graph-${Math.random().toString(36).slice(2)}`, highlightMermaid(mermaid, nodes ?? []));
        if (live) {
          setSvg(out.svg);
          setFailed(false);
        }
      } catch {
        if (live) setFailed(true);
      }
    })();
    return () => {
      live = false;
    };
  }, [mermaid, nodes]);

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
        Thread
        <select
          value={threadId ?? ""}
          onChange={(e) => setPicked(e.target.value)}
          disabled={!threads.data?.length}
          className="rounded-md border border-border bg-panel px-2 py-1 font-mono text-xs text-foreground"
        >
          {!threads.data?.length && <option value="">No threads in this world yet</option>}
          {threads.data?.map((t) => (
            <option key={t.thread_id} value={t.thread_id} title={t.thread_id}>
              {threadLabel(t)}
            </option>
          ))}
        </select>
      </label>
      {failed || !mermaid ? (
        <pre className="m-0 max-h-[360px] overflow-auto rounded-lg border border-border bg-well p-3 font-mono text-xs leading-[1.55] text-prose-muted">
          {mermaid || "The graph is not available."}
        </pre>
      ) : (
        <div
          aria-label="Agent graph diagram"
          className="overflow-auto rounded-lg border border-border bg-well p-3"
          dangerouslySetInnerHTML={{ __html: svg ?? "" }}
        />
      )}
      <p className="m-0 text-xs text-muted-foreground">
        {run.isError
          ? "Could not load the last run."
          : nodes?.length
            ? `Last run: ${nodes.join(" → ")}${run.data?.paused ? " (waiting for approval)" : ""}`
            : threadId
              ? "No run yet for this thread."
              : "Pick a thread to see its last run."}
      </p>
    </div>
  );
}
