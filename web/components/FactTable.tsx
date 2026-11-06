"use client";

import Link from "next/link";
import { Fragment, useState, type ReactNode } from "react";
import { EntityChip } from "@/components/EntityChip";
import type { FactResult, FactRow } from "@/lib/factRows";
import type { EntryType, Fact, Flag } from "@/lib/types";

/** An entry cited by a flag: a chip when its type is known, then its ID (R4.3). */
export function Cite({ id, title, type, secret }: { id: string; title: string; type?: EntryType; secret?: boolean }) {
  const [shown, setShown] = useState(false);
  if (!id) return null;
  const href = `/canon/${encodeURIComponent(id)}`;
  let chip: ReactNode;
  if (secret && !shown)
    chip = (
      <span className="inline-flex items-center gap-2">
        <span className="text-muted-foreground">
          <span aria-hidden="true">••••••</span>
          <span className="sr-only">hidden secret</span>
        </span>
        <button
          type="button"
          onClick={() => setShown(true)}
          aria-label="Show secret entry"
          className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
        >
          Show
        </button>
      </span>
    );
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

/** Which values on the card stay hidden until Show (R12.12). */
export interface SecretOf {
  /** A stored fact of this entry. */
  canon: (f: Fact) => boolean;
  /** A drafted fact. */
  proposed: (f: Fact) => boolean;
  /** A flag's existing value (from the cited entry). */
  existing: (f: Flag) => boolean;
  /** A flag's new value. */
  incoming: (f: Flag) => boolean;
  /** A flag's explanation and suggested fix. */
  text: (f: Flag) => boolean;
  /** The cited entry's title. */
  cite: (id: string) => boolean;
}

const KIND_LABEL: Record<Flag["kind"], string> = { conflict: "Conflict", retcon: "Retcon", note: "Note" };
const RESULT_TEXT: Record<FactResult, string> = {
  Matches: "text-muted-foreground",
  "Changed (retcon)": "text-event",
  Changed: "text-foreground",
  Conflict: "text-conflict font-semibold",
  "Possible conflict": "text-conflict",
  Note: "text-myth",
  New: "text-accent",
  Removed: "text-muted-foreground",
};
const PROPOSED_CELL: Partial<Record<FactResult, string>> = {
  Conflict: "bg-[#261e14] text-[#f7c48a]",
  "Possible conflict": "bg-[#261e14] text-[#f7c48a]",
  "Changed (retcon)": "bg-event-bg text-event",
};

const CELL = "px-3 py-2.5 align-top";
const HEAD = "px-3 py-2 text-left text-[11px] font-normal uppercase tracking-[0.9px] text-muted-foreground";
const DOT = (
  <span aria-hidden="true" className="text-muted-foreground">
    ·
  </span>
);

/** One entry per value; a value is masked if any source of it is. */
function unique(items: { value: string; secret: boolean }[]) {
  const out = new Map<string, boolean>();
  for (const { value, secret } of items) out.set(value, (out.get(value) ?? false) || secret);
  return [...out].map(([value, secret]) => ({ value, secret }));
}

function Values({ items, empty }: { items: { value: string; secret: boolean }[]; empty: string }) {
  const list = unique(items);
  if (list.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  return (
    <div className="flex flex-col gap-1">
      {list.map((v, i) => (
        <SecretValue key={i} value={v.value} secret={v.secret} />
      ))}
    </div>
  );
}

/** Fact · In canon · Proposed · Result: every fact the change touches, flags and fixes under their row (R12.3, R4.5). */
export function FactTable({
  rows,
  secretOf,
  typeOf,
}: {
  rows: FactRow[];
  secretOf: SecretOf;
  typeOf: (id: string) => EntryType | undefined;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-[10px] border border-border">
      <table className="w-full table-fixed border-collapse text-sm">
        <thead className="bg-[#1a1f1d]">
          <tr>
            {["Fact", "In canon", "Proposed", "Result"].map((h) => (
              <th key={h} scope="col" className={HEAD}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            // A retcon's existing value is one of this entry's own facts, already listed; any other
            // flag's values come from the cited entry, or stand in for a row with no own facts.
            const existing = [
              ...row.canon.map((f) => ({ value: f.value, secret: secretOf.canon(f) })),
              ...row.flags
                .filter((f) => f.existing_fact !== null && (f.kind !== "retcon" || !row.canon.length))
                .map((f) => ({ value: f.existing_fact as string, secret: secretOf.existing(f) })),
            ];
            const proposed =
              row.proposed.length || row.canon.length
                ? row.proposed.map((f) => ({ value: f.value, secret: secretOf.proposed(f) }))
                : row.flags
                    .filter((f) => f.new_fact !== null)
                    .map((f) => ({ value: f.new_fact as string, secret: secretOf.incoming(f) }));
            const own = [...row.canon, ...row.proposed];
            const keySecret = own.length > 0 && own.every((f) => f.status === "secret");
            return (
              <Fragment key={`${row.key}-${i}`}>
                <tr className="border-t border-border">
                  <td className={`${CELL} break-words text-muted-foreground`}>
                    <SecretValue value={row.key} secret={keySecret} />
                  </td>
                  <td className={CELL}>
                    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                      <Values items={existing} empty="Not set" />
                      {row.cite && (
                        <>
                          {DOT}
                          <Cite id={row.cite.id} title={row.cite.title} type={typeOf(row.cite.id)} secret={secretOf.cite(row.cite.id)} />
                        </>
                      )}
                    </div>
                  </td>
                  <td className={`${CELL} ${PROPOSED_CELL[row.result] ?? ""}`}>
                    <Values items={proposed} empty={row.canon.length ? "Removed" : "Not set"} />
                  </td>
                  <td className={`${CELL} text-[13px] ${RESULT_TEXT[row.result]}`}>{row.result}</td>
                </tr>
                {row.flags.length > 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 pb-3 pt-0">
                      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] text-[#c9c6bd]">
                        {row.flags.map((f, j) => (
                          <li key={j} className="flex flex-col gap-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <strong className="text-foreground">{KIND_LABEL[f.kind]}</strong>
                              {f.entry_id && f.entry_id !== row.cite?.id && (
                                <>
                                  {DOT}
                                  <Cite id={f.entry_id} title={f.title} type={typeOf(f.entry_id)} secret={secretOf.cite(f.entry_id)} />
                                </>
                              )}
                              {f.explanation && (
                                <>
                                  {DOT}
                                  <SecretValue value={f.explanation} secret={secretOf.text(f)} />
                                </>
                              )}
                            </div>
                            {f.suggested_fix && (
                              <div className="rounded-[10px] bg-panel-3 px-3.5 py-2">
                                <strong>Suggested fix:</strong> <SecretValue value={f.suggested_fix} secret={secretOf.text(f)} />
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
