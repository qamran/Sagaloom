"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOnlyNote } from "@/components/AdminOnlyNote";
import { ApiError, putSettings } from "@/lib/api";
import type { SettingsPatch, SettingsPayload } from "@/lib/types";

const FIELD = "min-h-9 rounded-md border border-border-strong bg-background px-2 py-1 text-[13px] text-foreground";
const BTN = "min-h-9 rounded-lg border border-border-strong px-3 text-[13px] text-foreground disabled:opacity-50";

const promptOf = (p: SettingsPayload) => p.settings.agent_system_prompt ?? p.defaults.agent_system_prompt;

/** Developer settings (R12.4): the agent's temperature, token cap and system prompt. Judge,
 * extractor and guard temperatures are pinned at 0 and have no inputs. */
export function SettingsPanel({ payload, readOnly = false }: { payload: SettingsPayload; readOnly?: boolean }) {
  const qc = useQueryClient();
  const [base, setBase] = useState(payload);
  const [temp, setTemp] = useState(String(payload.settings.agent_temperature));
  const [tokens, setTokens] = useState(payload.settings.agent_max_tokens?.toString() ?? "");
  const [prompt, setPrompt] = useState(promptOf(payload));
  const [budget, setBudget] = useState(String(payload.settings.monthly_budget_usd));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const t = temp.trim() === "" ? NaN : Number(temp);
  const tempOk = Number.isFinite(t) && t >= 0 && t <= 2;
  const n = tokens.trim() === "" ? null : Number(tokens);
  const tokensOk = n === null || (Number.isInteger(n) && n >= 256 && n <= 16000);
  const promptOk = prompt.length >= 1 && prompt.length <= 8000;
  const b = budget.trim() === "" ? NaN : Number(budget);
  const budgetOk = Number.isFinite(b) && b >= 0;

  const patch: SettingsPatch = {};
  if (tempOk && t !== base.settings.agent_temperature) patch.agent_temperature = t;
  if (tokensOk && n !== base.settings.agent_max_tokens) patch.agent_max_tokens = n;
  if (promptOk && prompt !== promptOf(base)) patch.agent_system_prompt = prompt;
  if (budgetOk && b !== base.settings.monthly_budget_usd) patch.monthly_budget_usd = b;
  const valid = tempOk && tokensOk && promptOk && budgetOk;
  const dirty = Object.keys(patch).length > 0;
  const saveable = valid && dirty;

  /** `promptOnly` keeps unsaved temperature and token edits in their inputs. */
  function adopt(next: SettingsPayload, promptOnly = false) {
    setBase(next);
    if (!promptOnly) {
      setTemp(String(next.settings.agent_temperature));
      setTokens(next.settings.agent_max_tokens?.toString() ?? "");
      setBudget(String(next.settings.monthly_budget_usd));
    }
    setPrompt(promptOf(next));
    void qc.invalidateQueries({ queryKey: ["settings"], exact: true });
    void qc.invalidateQueries({ queryKey: ["studio"] });
    void qc.invalidateQueries({ queryKey: ["me"], exact: true });
  }

  async function send(body: SettingsPatch, promptOnly = false) {
    setError(null);
    setSaving(true);
    try {
      adopt(await putSettings(body), promptOnly);
    } catch (e) {
      setError(
        e instanceof ApiError && e.detail ? e.detail : "Settings were not saved. Check the values and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      id="settings"
      aria-label="Settings"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Settings</h2>
      <p className="m-0 text-xs text-muted-foreground">
        These apply to the chat agent from the next turn. The judge, extractor and guard always run at
        temperature 0.
      </p>
      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Agent temperature
          <input
            type="number"
            step="0.1"
            min={0}
            max={2}
            value={temp}
            aria-label="Agent temperature"
            aria-invalid={!tempOk}
            disabled={readOnly}
            onChange={(e) => setTemp(e.target.value)}
            className={`${FIELD} w-28`}
          />
          <span>0 to 2</span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Agent max tokens
          <input
            type="number"
            step="1"
            value={tokens}
            placeholder="Provider default"
            aria-label="Agent max tokens"
            aria-invalid={!tokensOk}
            disabled={readOnly}
            onChange={(e) => setTokens(e.target.value)}
            className={`${FIELD} w-40`}
          />
          <span>256 to 16000, empty for the provider default</span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Monthly AI budget (US$)
          <input
            type="number"
            step="0.25"
            min={0}
            value={budget}
            aria-label="Monthly AI budget (US$)"
            aria-invalid={!budgetOk}
            disabled={readOnly}
            onChange={(e) => setBudget(e.target.value)}
            className={`${FIELD} w-28`}
          />
          <span>per account per month; the admin has no limit</span>
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Agent system prompt
        <textarea
          rows={10}
          value={prompt}
          aria-label="Agent system prompt"
          aria-invalid={!promptOk}
          disabled={readOnly}
          onChange={(e) => setPrompt(e.target.value)}
          className={`${FIELD} font-mono text-xs leading-[1.55]`}
        />
        <span>
          {base.settings.agent_system_prompt === null ? "Built-in prompt" : "Custom prompt"} · 1 to 8000
          characters
        </span>
      </label>
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={BTN}
          disabled={readOnly || !saveable || saving}
          aria-describedby={saveable || readOnly ? undefined : "save-why"}
          onClick={() => void send(patch)}
        >
          Save
        </button>
        <button
          type="button"
          className={BTN}
          disabled={readOnly || base.settings.agent_system_prompt === null || saving}
          onClick={() => void send({ reset_system_prompt: true }, true)}
        >
          Reset to default
        </button>
      </div>
      {readOnly && <AdminOnlyNote />}
      {!readOnly && !saveable && (
        <p id="save-why" className="m-0 text-xs text-muted-foreground">{valid ? "No changes to save" : "Fix the highlighted value"}</p>
      )}
    </section>
  );
}
