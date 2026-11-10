"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { forgetMemory, getMemory } from "@/lib/api";
import { useWorld } from "@/lib/world";

/** Studio Memory section (R10.1, R10.2): short-term checkpointer stats and the world's
 * long-term author preferences, each with a Delete. */
export function MemoryPanel() {
  const { world } = useWorld();
  const worldId = world?.id;
  const qc = useQueryClient();
  const memory = useQuery({
    queryKey: ["memory", worldId],
    queryFn: () => getMemory(worldId as string),
    enabled: !!worldId,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function del(key: string, item?: string) {
    if (!worldId) return;
    setError(null);
    setBusy(`${key}:${item}`);
    try {
      await forgetMemory(worldId, key, item);
      void qc.invalidateQueries({ queryKey: ["memory", worldId] });
    } catch {
      setError("The preference was not deleted. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const rows = Object.entries(memory.data?.preferences ?? {}).flatMap(([key, v]) =>
    Array.isArray(v) ? v.map((item) => ({ key, value: item })) : [{ key, value: v }],
  );
  const st = memory.data?.short_term;

  return (
    <section
      id="memory"
      aria-label="Memory"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Memory</h2>
      {memory.isError && <p className="m-0 text-xs text-conflict">Could not load memory.</p>}
      {memory.isLoading && <p className="m-0 text-xs text-muted-foreground">Loading memory…</p>}
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      {st && (
        <p className="m-0 text-xs text-muted-foreground">
          Short-term: a SQLite checkpointer
          {st.threads != null && `, ${st.threads} ${st.threads === 1 ? "thread" : "threads"}`}
          {st.checkpoint_file && (
            <>
              {" in "}
              <span className="font-mono">{st.checkpoint_file}</span>
            </>
          )}
        </p>
      )}
      {memory.data && (
        <>
          <h3 className="m-0 text-[13px] font-medium">
            Long-term preferences ({memory.data.count}/{memory.data.cap})
          </h3>
          {rows.length === 0 ? (
            <p className="m-0 text-xs text-muted-foreground">No preferences yet. Say &quot;remember …&quot; in chat.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {rows.map((r) => (
                <li key={`${r.key}:${r.value}`} className="flex flex-wrap items-center gap-3 text-xs">
                  <span className="font-mono">{r.key}</span>
                  <span className="min-w-0 flex-1">{r.value}</span>
                  <button
                    type="button"
                    aria-label={`Delete ${r.key}: ${r.value}`}
                    onClick={() => void del(r.key, r.value)}
                    disabled={busy === `${r.key}:${r.value}`}
                    aria-busy={busy === `${r.key}:${r.value}`}
                    className="rounded-md border border-border-strong px-2 py-1 text-muted-foreground disabled:opacity-50"
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
