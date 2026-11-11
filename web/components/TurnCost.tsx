"use client";

import { useState } from "react";
import { stepsFromRoles } from "@/lib/steps";
import type { TurnUsage } from "@/lib/types";

const n = (v: number) => v.toLocaleString("en-US");
const usd = (v: number) => `$${v.toFixed(4)}`;
const plural = (count: number, word: string) => `${count} ${count === 1 ? word : `${word}s`}`;

/**
 * One turn's cost, under its last shown message (M4, design §3.2): a muted line that opens into a
 * stacked bar and one row per pipeline step. Nothing for a turn without model calls.
 */
export function TurnCost({ turn }: { turn: TurnUsage }) {
  const [open, setOpen] = useState(false);
  const steps = stepsFromRoles(turn.by_role);
  if (steps.length === 0) return null;
  const tokens = turn.usage.prompt_tokens + turn.usage.completion_tokens;
  const spent = steps.reduce((sum, s) => sum + s.cost_usd, 0);

  return (
    <div className="flex flex-col gap-2 text-xs text-muted-foreground">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="self-start pl-0.5 text-left tabular-nums hover:text-foreground"
      >
        {n(tokens)} tokens · {usd(turn.usage.cost_usd)} · {plural(steps.length, "step")}{" "}
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="flex max-w-[420px] flex-col gap-2.5 rounded-lg border border-border bg-panel-2 px-3 py-2.5">
          <div aria-hidden="true" className="flex h-1.5 overflow-hidden rounded-full bg-panel-3">
            {steps.map((s) => (
              <div
                key={s.key}
                className={`h-full ${s.bar}`}
                style={{ width: `${spent > 0 ? (s.cost_usd / spent) * 100 : 100 / steps.length}%` }}
              />
            ))}
          </div>
          <table aria-label="Cost by step" className="w-full border-collapse tabular-nums">
            <tbody>
              {steps.map((s) => (
                <tr key={s.key}>
                  <th scope="row" className="py-0.5 pr-3 text-left font-normal text-foreground">
                    <span aria-hidden="true" className={`mr-1.5 inline-block size-2 rounded-sm ${s.bar}`} />
                    {s.name}
                  </th>
                  <td className="py-0.5 pr-3">{plural(s.calls, "call")}</td>
                  <td className="py-0.5 pr-3">
                    {n(s.prompt_tokens)} → {n(s.completion_tokens)}
                  </td>
                  <td className="py-0.5 text-right text-foreground">{usd(s.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-border">
                <th scope="row" className="pt-1.5 pr-3 text-left font-semibold text-foreground">
                  Total
                </th>
                <td className="pt-1.5 pr-3">{plural(steps.reduce((sum, s) => sum + s.calls, 0), "call")}</td>
                <td className="pt-1.5 pr-3">
                  {n(turn.usage.prompt_tokens)} → {n(turn.usage.completion_tokens)}
                </td>
                <td className="pt-1.5 text-right font-semibold text-foreground">{usd(turn.usage.cost_usd)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
