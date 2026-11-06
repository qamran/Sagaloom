"use client";

import { ImportProgress } from "@/components/ImportProgress";
import { ImportSourceCard } from "@/components/ImportSourceCard";
import { RecentImports } from "@/components/RecentImports";
import { useImport } from "@/lib/useImport";
import { useWorld } from "@/lib/world";

/** Bring existing notes in: every candidate becomes a proposal that waits in Review. */
export default function ImportPage() {
  const { world } = useWorld();
  const run = useImport();
  const running = run.phase === "extracting" || run.phase === "checking";
  const start = (body: { text: string; filename?: string }) => {
    if (world) void run.start(world.id, body);
  };
  return (
    <main className="flex flex-col gap-5 px-4 py-6 md:px-11 md:py-[30px]">
      <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">Import</h1>
      {run.error && (
        <p role="alert" className="m-0 text-conflict">
          {run.error}
        </p>
      )}
      {running ? (
        <ImportProgress phase={run.phase} candidates={run.candidates} skipped={run.skipped} events={run.events} />
      ) : (
        <div className="flex flex-wrap items-stretch gap-4">
          <ImportSourceCard kind="paste" disabled={!world} onExtract={start} />
          <ImportSourceCard kind="upload" disabled={!world} onExtract={start} />
          <ImportSourceCard kind="wiki" />
        </div>
      )}
      <RecentImports />
    </main>
  );
}
