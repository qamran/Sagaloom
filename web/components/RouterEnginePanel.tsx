"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOnlyNote } from "@/components/AdminOnlyNote";
import { putSettings } from "@/lib/api";
import type { DevSettings, SettingsPayload } from "@/lib/types";

const OPTIONS: { value: DevSettings["router_engine"]; label: string }[] = [
  { value: "llm", label: "LLM (default)" },
  { value: "jev", label: "Jev decision model" },
];

/** The router engine (R6.6): which engine decides brainstorm, query or edit each turn. */
export function RouterEnginePanel({ payload, readOnly }: { payload: SettingsPayload; readOnly: boolean }) {
  const qc = useQueryClient();
  const [engine, setEngine] = useState(payload.settings.router_engine);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function choose(next: DevSettings["router_engine"]) {
    setError(null);
    setSaving(true);
    try {
      const saved = await putSettings({ router_engine: next });
      setEngine(saved.settings.router_engine);
      void qc.invalidateQueries({ queryKey: ["settings"], exact: true });
      void qc.invalidateQueries({ queryKey: ["studio"] });
    } catch {
      setError("The router engine was not saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <fieldset
        role="radiogroup"
        aria-label="Router engine"
        className="m-0 flex flex-wrap items-center gap-x-5 gap-y-2 border-0 p-0 text-[13px] text-foreground"
      >
        {OPTIONS.map((o) => (
          <label key={o.value} className="flex items-center gap-2">
            <input
              type="radio"
              name="router-engine"
              value={o.value}
              checked={engine === o.value}
              disabled={readOnly || saving}
              onChange={() => void choose(o.value)}
            />
            {o.label}
          </label>
        ))}
      </fieldset>
      <p className="m-0 text-xs text-muted-foreground">
        Jev answers one typed question (brainstorm, query or edit) with a confidence, instead of a prompt to a chat
        model. If Jev fails, the LLM decides that turn.
      </p>
      {readOnly && <AdminOnlyNote />}
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
    </div>
  );
}
