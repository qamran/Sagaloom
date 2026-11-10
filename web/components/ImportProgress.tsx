"use client";

import { useState } from "react";
import { UnderTheHood } from "@/components/UnderTheHood";
import { viewFromEvents } from "@/lib/turns";
import type { SseEvent } from "@/lib/types";
import type { ImportPhase } from "@/lib/useImport";

/** What a running import is doing: extracting, then checking each proposal against canon. */
export function ImportProgress({
  phase,
  candidates,
  skipped,
  events,
  worldId,
}: {
  phase: ImportPhase;
  candidates: number | null;
  skipped: number | null;
  events: SseEvent[];
  /** The world being imported into: the drawer's secrets follow it. */
  worldId?: string;
}) {
  const [hood, setHood] = useState(false);
  return (
    <section
      aria-label="Import progress"
      className="flex max-w-3xl flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <div role="status" aria-live="polite">
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[15px]">
          <li>Extracting entries…</li>
          {candidates !== null && (
            <li>
              Found {candidates} {candidates === 1 ? "candidate" : "candidates"} ({skipped ?? 0} not imported)
            </li>
          )}
          {phase === "checking" && candidates !== null && (
            <li>
              Checking {candidates} {candidates === 1 ? "proposal" : "proposals"} against canon…
            </li>
          )}
        </ul>
      </div>
      <div>
        <button
          type="button"
          onClick={() => setHood(true)}
          className="min-h-11 rounded-lg border border-border-strong px-4 text-[13px] text-foreground hover:bg-panel-3"
        >
          Under the hood
        </button>
      </div>
      {hood && (
        <UnderTheHood
          turn={viewFromEvents({ turn: 1, kind: "message", events })}
          worldId={worldId}
          onClose={() => setHood(false)}
        />
      )}
    </section>
  );
}
