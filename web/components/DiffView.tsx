"use client";

import { diffWords } from "diff";
import { useState } from "react";
import { TYPE_LABEL } from "@/lib/entity";
import type { LineField } from "@/lib/factRows";
import type { EntryType } from "@/lib/types";

const FIELD_LABEL: Record<LineField, string> = { title: "Title", type: "Type", status: "Status", aliases: "Aliases" };
const display = (field: LineField, v: string) => (field === "type" ? (TYPE_LABEL[v as EntryType] ?? v) : v);

/** Changed one-line fields: old struck through, new highlighted. */
export function LineDiff({ changes }: { changes: { field: LineField; old: string; new: string }[] }) {
  if (changes.length === 0) return null;
  return (
    <dl className="m-0 flex flex-col gap-1.5 text-sm">
      {changes.map((c) => (
        <div key={c.field} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <dt className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">{FIELD_LABEL[c.field]}</dt>
          <dd className="m-0 flex flex-wrap items-baseline gap-2">
            <span className="line-through text-muted-foreground">{display(c.field, c.old)}</span>
            <span aria-hidden="true" className="text-muted-foreground">
              →
            </span>
            <span className="rounded px-1 text-foreground bg-accent/15">{display(c.field, c.new)}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Word diff of an entry body, open when it changed; a secret entry's diff stays behind one Show. */
export function BodyDiff({ before, after, secret }: { before: string; after: string; secret: boolean }) {
  const [shown, setShown] = useState(false);
  if (before === after) return null;
  return (
    <details open className="rounded-[10px] border border-border px-3.5 py-3 text-sm">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[1px]">Body changes</summary>
      {secret && !shown ? (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-muted-foreground">
            <span aria-hidden="true">••••••</span>
            <span className="sr-only">hidden secret</span>
          </span>
          <button
            type="button"
            onClick={() => setShown(true)}
            aria-label="Show secret body changes"
            className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
          >
            Show
          </button>
        </div>
      ) : (
        <p className="m-0 mt-2 whitespace-pre-line font-heading text-[15px] text-[#e3dfd5]">
          {diffWords(before, after).map((part, i) =>
            part.added ? (
              <ins key={i} className="rounded bg-accent/15 text-foreground no-underline">
                <span className="sr-only">added: </span>
                {part.value}
              </ins>
            ) : part.removed ? (
              <del key={i} className="text-muted-foreground">
                <span className="sr-only">removed: </span>
                {part.value}
              </del>
            ) : (
              <span key={i}>{part.value}</span>
            ),
          )}
        </p>
      )}
    </details>
  );
}
