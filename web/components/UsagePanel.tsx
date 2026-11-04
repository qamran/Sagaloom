import type { StudioData } from "@/lib/types";

const ROLE_SHORT: Record<string, string> = { agent: "Agent", judge: "Judge", extractor: "Extractor", guard: "Guard" };

/** "Judge (Luna)" for role judge on openai/gpt-6-luna; the bare model id when the role is unknown. */
export function usageLabel(role: string | null | undefined, model: string): string {
  const short = (model.split("/").pop() ?? model).replace(/^gpt-[\d.]+-/, "");
  const name = short.charAt(0).toUpperCase() + short.slice(1);
  return role && ROLE_SHORT[role] ? `${ROLE_SHORT[role]} (${name})` : model;
}

const n = (v: number) => v.toLocaleString("en-US");

/** Usage (R20.4): totals over every recorded model call, and the cost split by model. */
export function UsagePanel({ usage }: { usage: StudioData["usage"] }) {
  const max = Math.max(0, ...usage.by_model.map((m) => m.cost_usd));
  return (
    <section
      id="usage"
      aria-label="Usage"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Usage</h2>
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
          Cost by model
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
