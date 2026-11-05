"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { forgetMemory } from "@/lib/api";
import type { MemoryResult } from "@/lib/types";

/** One `remember` result: a stored preference shows a chip with Undo; a refused one is muted
 * text. Both read the item's `note`, never the agent-facing message content. */
export function RememberedChip({ worldId, result }: { worldId?: string; result: MemoryResult }) {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "busy" | "forgotten" | "failed">("idle");

  if (!result.stored) return <span className="text-xs text-muted-foreground">{result.note}</span>;

  async function undo() {
    if (!worldId) return;
    setState("busy");
    try {
      // Always name the value: a stale Undo must not remove a newer tone or genre.
      await forgetMemory(worldId, result.key, result.value);
      setState("forgotten");
      void qc.invalidateQueries({ queryKey: ["memory", worldId] });
    } catch {
      setState("failed");
    }
  }

  if (state === "forgotten") {
    return (
      <span role="status" className="text-xs text-muted-foreground">
        Forgotten
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-panel-3 px-3 py-1 text-xs">
      <span>{result.note}</span>
      <button
        type="button"
        aria-label={`Undo ${result.note}`}
        onClick={() => void undo()}
        disabled={!worldId || state === "busy"}
        className="text-myth underline"
      >
        Undo
      </button>
      {state === "failed" && (
        <span role="alert" className="text-conflict">
          Could not undo. Try again.
        </span>
      )}
    </span>
  );
}
