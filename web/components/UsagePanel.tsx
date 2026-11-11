import { spendLine } from "@/lib/me";
import { stepName, stepOf } from "@/lib/steps";
import type { Me, StudioData } from "@/lib/types";
import type { Scope } from "@/lib/api";

/** "Check (Luna)" for role judge on openai/gpt-6-luna; the bare model id when the role is unknown. */
export function usageLabel(role: string | null | undefined, model: string): string {
  const bare = model.split("/").pop() ?? model;
  const gpt = /^gpt-[\d.]+-/.test(bare); // "gpt-6-luna" reads as "Luna"; other vendors keep their id
  const short = gpt ? bare.replace(/^gpt-[\d.]+-/, "") : bare;
  const name = gpt ? short.charAt(0).toUpperCase() + short.slice(1) : short;
  if (!role) return model;
  const key = stepOf(role);
  return key === "other" ? model : `${stepName(key)} (${name})`;
}

const n = (v: number) => v.toLocaleString("en-US");

/** Usage (R20.4): totals over every recorded model call, and the cost split by step. */
export function UsagePanel({
  usage,
  me,
  scope = "mine",
  onScope,
}: {
  usage: StudioData["usage"];
  /** The account, for the "This month" line. */
  me?: Me;
  scope?: Scope;
  /** Given only to the admin: adds the "All users" switch. */
  onScope?: (scope: Scope) => void;
}) {
  const max = Math.max(0, ...usage.by_model.map((m) => m.cost_usd));
  return (
    <section
      id="usage"
      aria-label="Usage"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Usage</h2>
      {me && <p className="m-0 text-[13px] text-muted-foreground">{spendLine(me)}</p>}
      {onScope && (
        <label className="flex items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            role="switch"
            checked={scope === "all"}
            onChange={(e) => onScope(e.target.checked ? "all" : "mine")}
          />
          All users
        </label>
      )}
      <dl className="m-0 grid grid-cols-3 gap-2.5">
        {[
          ["Tokens in", n(usage.prompt_tokens)],
          ["Tokens out", n(usage.completion_tokens)],
          ["Cost", `$${usage.cost_usd.toFixed(4)}`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-border bg-panel px-3 py-2">
            <dt className="text-[11px] uppercase tracking-[0.8px] text-muted-foreground">{label}</dt>
            <dd className="m-0 text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-2">
        <h3 className="m-0 text-[11px] font-medium uppercase tracking-[0.9px] text-muted-foreground">
          Cost by step
        </h3>
        {usage.by_model.length === 0 && (
          <p className="m-0 text-[13px] text-muted-foreground">No model calls yet. Send a chat message first.</p>
        )}
        {usage.by_model.map((m) => (
          <div key={`${m.role ?? ""}|${m.model}`} className="flex flex-col gap-1 text-xs">
            <div className="flex justify-between gap-2">
              <span className="font-mono">{usageLabel(m.role, m.model)}</span>
              <span className="text-muted-foreground">
                {m.calls} {m.calls === 1 ? "call" : "calls"} · {n(m.prompt_tokens)} → {n(m.completion_tokens)} tok ·{" "}
                <span className="text-foreground">${m.cost_usd.toFixed(4)}</span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-panel-3">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${max > 0 ? Math.max(3, (m.cost_usd / max) * 100) : 3}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
