"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOnlyNote } from "@/components/AdminOnlyNote";
import { getTools, putSettings } from "@/lib/api";
import type { ToolInfo } from "@/lib/types";

/** The agent's tools (R11.G3): core tools are always on; the others have a switch that applies
 * from the next turn. A switch sends the full list of enabled optional tools. */
export function ToolsPanel({ readOnly = false }: { readOnly?: boolean }) {
  const qc = useQueryClient();
  const tools = useQuery({ queryKey: ["tools"], queryFn: getTools });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function toggle(target: ToolInfo) {
    const optional = (tools.data ?? []).filter((t) => !t.core);
    const next = optional
      .filter((t) => (t.name === target.name ? !t.enabled : t.enabled))
      .map((t) => t.name);
    setError(null);
    setSaving(true);
    try {
      await putSettings({ enabled_tools: next });
      void qc.invalidateQueries({ queryKey: ["tools"] });
      // Exact: ["settings", "models"] shares the prefix and a toggle must not refetch it.
      void qc.invalidateQueries({ queryKey: ["settings"], exact: true });
      void qc.invalidateQueries({ queryKey: ["studio"] });
    } catch {
      setError("The tool setting was not saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      id="tools"
      aria-label="Tools"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Tools</h2>
      <p className="m-0 text-xs text-muted-foreground">
        The agent can only use the tools that are on. A change applies from the next turn.
      </p>
      {readOnly && <AdminOnlyNote />}
      {tools.isError && <p className="m-0 text-xs text-conflict">Could not load the tools.</p>}
      {tools.isLoading && <p className="m-0 text-xs text-muted-foreground">Loading tools…</p>}
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {(tools.data ?? []).map((t) => (
          <li key={t.name} className="flex flex-wrap items-start gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={t.enabled}
              aria-label={t.name}
              disabled={t.core || saving || readOnly}
              onClick={() => void toggle(t)}
              className={`min-h-9 min-w-24 rounded-full border px-4 text-[13px] ${
                t.enabled ? "border-myth text-myth" : "border-border-strong text-muted-foreground"
              }`}
            >
              {t.core ? "Always on" : t.enabled ? "On" : "Off"}
            </button>
            <div className="flex min-w-0 flex-[1_1_280px] flex-col gap-0.5">
              <span className="font-mono text-xs">{t.name}</span>
              <span className="whitespace-pre-line text-xs text-muted-foreground">{t.description}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
