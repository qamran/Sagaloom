"use client";

import { useState } from "react";
import { useWorldShowSecrets } from "@/lib/secrets";
import type { Fact, Status } from "@/lib/types";

const BADGE: Partial<Record<Status, string>> = {
  myth: "text-myth border-[#5b4785] bg-[#211c33]",
  rumour: "text-myth border-[#5b4785] bg-[#211c33]",
  secret: "text-conflict border-[#5a4228] bg-[#221c15]",
};

function FactRow({ fact, hidden, onShow }: { fact: Fact; hidden: boolean; onShow: () => void }) {
  const badge = fact.status !== "canon" ? BADGE[fact.status] : undefined;
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">{hidden ? "Secret fact" : fact.key}</div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {hidden ? (
          <>
            <span className="text-muted-foreground">
              <span aria-hidden="true">••••••••</span>
              <span className="sr-only">hidden secret</span>
            </span>
            <button
              type="button"
              onClick={onShow}
              aria-label="Show secret fact"
              className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
            >
              Show
            </button>
          </>
        ) : (
          <span>{fact.value}</span>
        )}
        {badge && (
          <span className={`rounded-md border px-1.5 text-[11px] ${badge}`}>{fact.status}</span>
        )}
        {fact.told_by && !hidden && (
          <span className="text-xs text-muted-foreground">told by {fact.told_by}</span>
        )}
      </div>
    </div>
  );
}

const factId = (f: Fact) => JSON.stringify([f.key, f.value]);

/**
 * key: value rows with a status badge. Secret facts stay hidden until Show is clicked or the
 * world toggle is on (R12.12); `hideAll` hides every fact, for a secret entry's draft.
 */
export function FactList({ facts, hideAll = false }: { facts: Fact[]; hideAll?: boolean }) {
  const [shown, setShown] = useState<Set<string>>(new Set());
  const worldShown = useWorldShowSecrets();
  if (facts.length === 0) {
    return <p className="m-0 text-sm text-muted-foreground">No facts recorded for this entry yet.</p>;
  }
  return (
    <div className="flex flex-col gap-3.5">
      {facts.map((f, i) => (
        <FactRow
          key={`${f.key}-${i}`}
          fact={f}
          hidden={(hideAll || f.status === "secret") && !worldShown && !shown.has(factId(f))}
          onShow={() => setShown((s) => new Set(s).add(factId(f)))}
        />
      ))}
    </div>
  );
}
