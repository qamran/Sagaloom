"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOnlyNote } from "@/components/AdminOnlyNote";
import { Toggle } from "@/components/Toggle";
import { TryIt } from "@/components/TryIt";
import { getTools, putSettings } from "@/lib/api";
import { TOOL_TESTS } from "@/lib/toolTests";
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
      <p className="m-0 max-w-3xl text-[13px] text-muted-foreground">
        The agent can only use the tools that are on; a change applies from the next turn. Each card has a message
        to try in Chat (examples use the sample world Velmar). Turn a tool Off and send it again to test the switch.
      </p>
      {readOnly && <AdminOnlyNote />}
      {tools.isError && <p className="m-0 text-xs text-conflict">Could not load the tools.</p>}
      {tools.isLoading && <p className="m-0 text-xs text-muted-foreground">Loading tools…</p>}
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 lg:grid-cols-2">
        {(tools.data ?? []).map((t) => {
          const test = TOOL_TESTS[t.name];
          return (
            <li key={t.name} className="flex flex-col gap-3 rounded-xl border border-border bg-panel p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="font-mono text-[13px] font-semibold text-foreground">{t.name}</span>
                  <span className="text-[13px] text-muted-foreground">{test?.summary ?? firstSentence(t.description)}</span>
                </div>
                {t.core ? (
                  <AlwaysOn />
                ) : (
                  <Toggle label={t.name} on={t.enabled} disabled={saving || readOnly} onChange={() => void toggle(t)} />
                )}
              </div>
              {test && <TryIt prompt={test.prompt} expect={test.expect} />}
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer select-none hover:text-foreground">What the agent is told</summary>
                <p className="m-0 mt-1.5 whitespace-pre-line leading-relaxed">{t.description}</p>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const firstSentence = (text: string) => text.split(/(?<=\.)\s/)[0];

/** A core tool's state: plain text with a lock, not a control, because it cannot be turned off. */
function AlwaysOn() {
  return (
    <span
      title="Core tool: the agent always has it, so it cannot be turned off."
      className="inline-flex shrink-0 items-center gap-1.5 py-1 text-xs text-muted-foreground"
    >
      <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 fill-current">
        <path d="M5 7V5a3 3 0 1 1 6 0v2h.5A1.5 1.5 0 0 1 13 8.5v5a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13.5v-5A1.5 1.5 0 0 1 4.5 7H5Zm1.5 0h3V5a1.5 1.5 0 0 0-3 0v2Z" />
      </svg>
      Always on
    </span>
  );
}
