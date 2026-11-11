"use client";

import { ImportProgress } from "@/components/ImportProgress";
import { ImportSourceCard } from "@/components/ImportSourceCard";
import { RecentImports } from "@/components/RecentImports";
import { overBudgetMessage, useMe } from "@/lib/me";
import { useImport, type ImportBody } from "@/lib/useImport";
import { useWorld } from "@/lib/world";

/** Bring existing notes in: every candidate becomes a proposal that waits in Review. */
export default function ImportPage() {
  const { world } = useWorld();
  const run = useImport();
  const overBudget = overBudgetMessage(useMe());
  const running = run.phase === "extracting" || run.phase === "checking";
  const start = (body: ImportBody) => {
    if (world) void run.start(world.id, body);
  };
  return (
    <main className="flex flex-col gap-5 px-4 py-6 md:px-11 md:py-[30px]">
      <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">Import</h1>
      {overBudget && (
        <p role="alert" className="m-0 rounded-xl border border-conflict-line bg-conflict-bg px-3.5 py-3 text-sm text-conflict-text">
          {overBudget}
        </p>
      )}
      {run.error && run.error !== overBudget && (
        <p role="alert" className="m-0 text-conflict">
          {run.error}
        </p>
      )}
      {running && (
        <ImportProgress
          phase={run.phase}
          candidates={run.candidates}
          skipped={run.skipped}
          events={run.events}
          worldId={run.worldId ?? undefined}
        />
      )}
      {/* Hidden, not unmounted, while running: a failed import keeps the pasted text and the chosen file. */}
      {/* Over budget the Extract buttons give way to the message above; the pasted text stays reachable on return. */}
      <div hidden={running || !!overBudget}>
        <div className="flex flex-wrap items-stretch gap-4">
          <ImportSourceCard kind="paste" disabled={!world} onExtract={start} />
          <ImportSourceCard kind="upload" disabled={!world} onExtract={start} />
          <ImportSourceCard kind="wiki" disabled={!world} onExtract={start} />
        </div>
      </div>
      <RecentImports />
    </main>
  );
}
