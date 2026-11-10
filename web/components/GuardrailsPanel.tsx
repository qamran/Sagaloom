"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getGuardLog, putSettings } from "@/lib/api";
import type { GuardLogRow, SettingsPayload } from "@/lib/types";

const BADGE: Record<GuardLogRow["verdict"], string> = {
  safe: "border-border text-muted-foreground",
  unsafe: "border-conflict text-conflict",
  injection: "border-conflict text-conflict",
  unknown: "border-border text-muted-foreground",
  error: "border-failed text-failed",
};

/** The input guard (R13.1): an on/off switch, the policy read-only, and the recent verdicts. */
export function GuardrailsPanel({ payload }: { payload: SettingsPayload }) {
  const qc = useQueryClient();
  const [on, setOn] = useState(payload.settings.guard_enabled);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const log = useQuery({ queryKey: ["guard-log"], queryFn: () => getGuardLog(20) });

  async function toggle() {
    setError(null);
    setSaving(true);
    try {
      const next = await putSettings({ guard_enabled: !on });
      setOn(next.settings.guard_enabled);
      void qc.invalidateQueries({ queryKey: ["settings"], exact: true });
      void qc.invalidateQueries({ queryKey: ["studio"] });
    } catch {
      setError("The guard setting was not saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      id="guardrails"
      aria-label="Guardrails"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Guardrails</h2>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="Input guard"
          disabled={saving}
          onClick={() => void toggle()}
          className={`min-h-9 rounded-full border px-4 text-[13px] ${
            on ? "border-myth text-myth" : "border-border-strong text-muted-foreground"
          }`}
        >
          {on ? "On" : "Off"}
        </button>
        <span className="text-xs text-muted-foreground">
          Checks every chat message for real-world harm and prompt injection before the agent sees it. Fails
          closed.
        </span>
      </div>
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      <div className="text-xs uppercase tracking-[0.8px] text-muted-foreground">Policy (read-only)</div>
      <pre className="m-0 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-background p-3 font-mono text-xs leading-[1.55] text-muted-foreground">
        {payload.guard_policy}
      </pre>
      <div className="text-xs uppercase tracking-[0.8px] text-muted-foreground">Recent verdicts</div>
      {log.isError && <p className="m-0 text-xs text-conflict">Could not load the guard log.</p>}
      {log.data && log.data.length === 0 && <p className="m-0 text-xs text-muted-foreground">No messages checked yet.</p>}
      {log.data && log.data.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[13px]">
          {log.data.map((r, i) => (
            <li key={`${r.thread_id}-${r.started_at}-${i}`} className="flex flex-wrap items-center gap-2.5">
              <span className={`rounded-full border px-2 py-px text-[11px] ${BADGE[r.verdict]}`}>{r.verdict}</span>
              <span className="font-mono text-xs">{r.thread_id}</span>
              <span className="text-xs text-muted-foreground">{r.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
