"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { EntityChip } from "@/components/EntityChip";
import type { EntryType, Flag } from "@/lib/types";

/** An entry cited by a flag: a chip when its type is known, then its ID (R4.3). */
export function Cite({ id, title, type, secret }: { id: string; title: string; type?: EntryType; secret?: boolean }) {
  if (!id) return null;
  const href = `/canon/${encodeURIComponent(id)}`;
  let chip: ReactNode;
  if (secret) chip = <span className="text-muted-foreground">Secret entry</span>;
  else if (type) chip = <EntityChip type={type} name={title} href={href} />;
  else
    chip = (
      <Link
        href={href}
        className="inline-flex items-center rounded-md border border-border-strong bg-panel-3 px-2 py-0.5 text-[13px] text-foreground no-underline hover:brightness-125"
      >
        {title}
      </Link>
    );
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {chip}
      <span className="text-xs text-muted-foreground">{id}</span>
    </span>
  );
}

/** A value that may be secret: hidden until Show, like FactList (R12.12). */
export function SecretValue({ value, secret, className }: { value: string; secret: boolean; className?: string }) {
  const [shown, setShown] = useState(false);
  if (!secret || shown) return <span className={className}>{value}</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-muted-foreground">
        <span aria-hidden="true">••••••</span>
        <span className="sr-only">hidden secret</span>
      </span>
      <button
        type="button"
        onClick={() => setShown(true)}
        aria-label="Show secret fact"
        className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
      >
        Show
      </button>
    </span>
  );
}

export interface FactTableRow {
  flag: Flag;
  /** Type of the cited entry, when known. */
  type?: EntryType;
  existingSecret: boolean;
  proposedSecret: boolean;
  citeSecret: boolean;
}

const KIND_LABEL: Record<Flag["kind"], string> = { conflict: "Conflict", retcon: "Retcon", note: "Note" };
const KIND_TEXT: Record<Flag["kind"], string> = {
  conflict: "text-conflict",
  retcon: "text-event",
  note: "text-myth",
};
const PROPOSED_CELL: Record<Flag["kind"], string> = {
  conflict: "bg-[#261e14] text-[#f7c48a]",
  retcon: "bg-event-bg text-event",
  note: "",
};

const CELL = "px-3 py-2.5 align-top";
const HEAD = "px-3 py-2 text-left text-[11px] font-normal uppercase tracking-[0.9px] text-muted-foreground";

/** Fact · In canon · Proposed, one row per flag that names a fact (R12.3). */
export function FactTable({ rows }: { rows: FactTableRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-[10px] border border-border">
      <table className="w-full table-fixed border-collapse text-sm">
        <thead className="bg-[#1a1f1d]">
          <tr>
            <th scope="col" className={HEAD}>
              Fact
            </th>
            <th scope="col" className={HEAD}>
              In canon
            </th>
            <th scope="col" className={HEAD}>
              Proposed
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ flag, type, existingSecret, proposedSecret, citeSecret }, i) => (
            <tr key={`${flag.kind}-${flag.entry_id}-${flag.fact_key}-${i}`} className="border-t border-border">
              <td className={`${CELL} text-muted-foreground`}>
                <div className="break-words">{flag.fact_key}</div>
                <div className={`text-[11px] ${KIND_TEXT[flag.kind]}`}>{KIND_LABEL[flag.kind]}</div>
              </td>
              <td className={CELL}>
                <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                  {flag.existing_fact !== null ? (
                    <SecretValue value={flag.existing_fact} secret={existingSecret} />
                  ) : (
                    <span className="text-muted-foreground">Not set</span>
                  )}
                  <span aria-hidden="true" className="text-muted-foreground">
                    ·
                  </span>
                  <Cite id={flag.entry_id} title={flag.title} type={type} secret={citeSecret} />
                </div>
              </td>
              <td className={`${CELL} ${PROPOSED_CELL[flag.kind]}`}>
                {flag.new_fact !== null ? (
                  <SecretValue value={flag.new_fact} secret={proposedSecret} />
                ) : (
                  <span className="text-muted-foreground">Removed</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
