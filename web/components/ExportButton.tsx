"use client";

import { useState } from "react";
import { exportUrl } from "@/lib/api";

/** Markdown zip download for the current world, with an option to leave secrets out (R11.5). */
export function ExportButton({ worldId }: { worldId: string }) {
  const [leaveOut, setLeaveOut] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-4 text-sm">
      <a
        href={exportUrl(worldId, leaveOut)}
        download
        className="rounded-md border border-border-strong bg-transparent px-3 py-1.5 text-foreground hover:bg-panel-3"
      >
        Download as Markdown
      </a>
      <label className="flex items-center gap-2 text-muted-foreground">
        <input type="checkbox" checked={leaveOut} onChange={(e) => setLeaveOut(e.target.checked)} />
        Leave out secrets
      </label>
    </div>
  );
}
