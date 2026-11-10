"use client";

import Link from "next/link";
import { Fragment, useState, type ReactNode } from "react";
import { EntityChip } from "@/components/EntityChip";
import type { FactResult, FactRow } from "@/lib/factRows";
import { useWorldShowSecrets } from "@/lib/secrets";
import type { EntryType, Fact, Flag } from "@/lib/types";

/**
 * An entry cited by a flag: a chip when its type is known, then its ID (R4.3). A secret title is
 * masked; `revealable={false}` drops its Show, for a title another control reveals (the card's
 * one Show for its own entry).
 */
export function Cite({
  id,
  title,
  type,
  secret,
  revealable = true,
}: {
  id: string;
  title: string;
  type?: EntryType;
  secret?: boolean;
  revealable?: boolean;
}) {
  const [shown, setShown] = useState(false);
  const worldShown = useWorldShowSecrets();
  if (!id) return null;
  const href = `/canon/${encodeURIComponent(id)}`;
  let chip: ReactNode;
  if (secret && !worldShown && !shown)
    chip = (
      <span className="inline-flex items-center gap-2">
        <span className="text-muted-foreground">
          <span aria-hidden="true">••••••</span>
          <span className="sr-only">hidden secret</span>
        </span>
        {revealable && (
          <button
            type="button"
            onClick={() => setShown(true)}
            aria-label="Show secret entry"
            className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
          >
            Show
          </button>
        )}
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

/**
 * A value that may be secret: hidden until Show, like FactList (R12.12). `children` (a status
 * tag, a teller) render after the value and stay hidden with it. `revealable={false}` drops the
 * Show, for a value hidden with its entry and revealed by the card's one Show.
 */
export function SecretValue({
  value,
  secret,
  revealable = true,
  className,
  children,
}: {
  value: string;
  secret: boolean;
  revealable?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const [shown, setShown] = useState(false);
  const worldShown = useWorldShowSecrets();
  if (!secret || worldShown || shown) {
    if (!children) return <span className={className}>{value}</span>;
    return (
      <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1">
        <span className={className}>{value}</span>
        {children}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-muted-foreground">
        <span aria-hidden="true">••••••</span>
        <span className="sr-only">hidden secret</span>
      </span>
      {revealable && (
        <button
          type="button"
          onClick={() => setShown(true)}
          aria-label="Show secret fact"
          className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
        >
          Show
        </button>
      )}
    </span>
  );
}

export const KIND_LABEL: Record<Flag["kind"], string> = { conflict: "Conflict", retcon: "Retcon", note: "Note" };

/** A flag's suggested fix: guidance only, never an action (R4.5). */
export function FlagFix({ fix, secret }: { fix: string; secret: boolean }) {
  return (
    <div className="rounded-[10px] bg-panel-3 px-3.5 py-2">
      <strong>Suggested fix:</strong> <SecretValue value={fix} secret={secret} />
    </div>
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
  /** A flag's explanation and suggested fix, as far as its existing side goes. */
  text: (f: Flag) => boolean;
  /** The cited entry's title. */
  cite: (id: string) => boolean;
  /** The cited entry is the proposal's own: its title has no Show, the card's one Show reveals it. */
  ownEntry: (id: string) => boolean;
}

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
  Conflict: "bg-conflict-bg-2 text-conflict-text-2",
  "Possible conflict": "bg-conflict-bg-2 text-conflict-text-2",
  "Changed (retcon)": "bg-event-bg text-event",
};
const STATUS_TAG: Record<Exclude<Fact["status"], "canon">, string> = {
  myth: "text-myth border-violet-line-strong bg-myth-bg",
  rumour: "text-myth border-violet-line-strong bg-myth-bg",
  secret: "text-conflict border-conflict-line bg-conflict-bg",
};

const CELL = "px-3 py-2.5 align-top";
const HEAD = "px-3 py-2 text-left text-[11px] font-normal uppercase tracking-[0.9px] text-muted-foreground";
const LIST = "m-0 flex list-none flex-col gap-1 p-0";
const DOT = (
  <span aria-hidden="true" className="text-muted-foreground">
    ·
  </span>
);

/** One value in a cell: a fact of this entry, or a flag's value with the entry it came from. */
interface Item {
  value: string | null;
  secret: boolean;
  status?: Fact["status"];
  toldBy?: string | null;
  cite?: { id: string; title: string };
}

const ofFact = (f: Fact, secret: boolean): Item => ({ value: f.value, secret, status: f.status, toldBy: f.told_by });

/** One item per (value, cited entry); an item is masked if any source of it is. */
function unique(items: Item[]) {
  const out = new Map<string, Item>();
  for (const it of items) {
    const k = JSON.stringify([it.value, it.status ?? null, it.toldBy ?? null, it.cite?.id ?? null]);
    const seen = out.get(k);
    out.set(k, seen ? { ...seen, secret: seen.secret || it.secret } : it);
  }
  return [...out.values()];
}

function Value({ item }: { item: Item }) {
  if (item.value === null) return null;
  const tag = item.status && item.status !== "canon" ? item.status : null;
  return (
    <SecretValue value={item.value} secret={item.secret}>
      {(tag || item.toldBy) && (
        <>
          {tag && <span className={`rounded-md border px-1.5 text-[11px] ${STATUS_TAG[tag]}`}>{tag}</span>}
          {item.toldBy && <span className="text-xs text-muted-foreground">told by {item.toldBy}</span>}
        </>
      )}
    </SecretValue>
  );
}

function Values({
  items,
  empty,
  typeOf,
  citeSecret,
  ownEntry,
}: {
  items: Item[];
  empty: string;
  typeOf: (id: string) => EntryType | undefined;
  citeSecret: (id: string) => boolean;
  ownEntry: (id: string) => boolean;
}) {
  const list = unique(items);
  if (list.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  return (
    <ul className={LIST}>
      {list.map((it, i) => (
        <li key={i} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          <Value item={it} />
          {it.cite && (
            <>
              {it.value !== null && DOT}
              <Cite
                id={it.cite.id}
                title={it.cite.title}
                type={typeOf(it.cite.id)}
                secret={citeSecret(it.cite.id)}
                revealable={!ownEntry(it.cite.id)}
              />
            </>
          )}
        </li>
      ))}
    </ul>
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
        <thead className="bg-raised">
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
            // A retcon's existing value is one of this entry's own facts (cited by none); every
            // other keyed flag comes from another entry, whose value sits next to its own Cite.
            const own = row.flags.filter((f) => f.kind === "retcon");
            const others = row.flags.filter((f) => f.kind !== "retcon");
            const existing: Item[] = [
              ...row.canon.map((f) => ofFact(f, secretOf.canon(f))),
              ...(row.canon.length ? [] : own)
                .filter((f) => f.existing_fact !== null)
                .map((f) => ({ value: f.existing_fact, secret: secretOf.existing(f) })),
              ...others.map((f) => ({
                value: f.existing_fact,
                secret: secretOf.existing(f),
                cite: { id: f.entry_id, title: f.title },
              })),
            ];
            const proposed: Item[] =
              row.proposed.length || row.canon.length
                ? row.proposed.map((f) => ofFact(f, secretOf.proposed(f)))
                : row.flags
                    .filter((f) => f.new_fact !== null)
                    .map((f) => ({ value: f.new_fact, secret: secretOf.incoming(f) }));
            const ownFacts = [...row.canon, ...row.proposed];
            const keySecret = ownFacts.length > 0 && ownFacts.every((f) => f.status === "secret");
            // Free text about a flag can restate either side (a retcon's explanation names the
            // added values), so it is masked when either side is.
            const draftSecret = row.proposed.some((f) => secretOf.proposed(f));
            const textSecret = (f: Flag) => secretOf.text(f) || secretOf.incoming(f) || draftSecret;
            const cells = { typeOf, citeSecret: secretOf.cite, ownEntry: secretOf.ownEntry };
            return (
              <Fragment key={`${row.key}-${i}`}>
                <tr className="border-t border-border">
                  <td className={`${CELL} break-words text-muted-foreground`}>
                    <SecretValue value={row.key} secret={keySecret} />
                  </td>
                  <td className={CELL}>
                    <Values items={existing} empty="Not set" {...cells} />
                  </td>
                  <td className={`${CELL} ${PROPOSED_CELL[row.result] ?? ""}`}>
                    <Values items={proposed} empty={row.canon.length ? "Removed" : "Not set"} {...cells} />
                  </td>
                  <td className={`${CELL} text-[13px] ${RESULT_TEXT[row.result]}`}>{row.result}</td>
                </tr>
                {row.flags.length > 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 pb-3 pt-0">
                      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] text-prose-muted">
                        {row.flags.map((f, j) => (
                          <li key={j} className="flex flex-col gap-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <strong className="text-foreground">{KIND_LABEL[f.kind]}</strong>
                              {f.kind === "retcon" && f.entry_id && (
                                <>
                                  {DOT}
                                  <Cite
                                    id={f.entry_id}
                                    title={f.title}
                                    type={typeOf(f.entry_id)}
                                    secret={secretOf.cite(f.entry_id)}
                                    revealable={!secretOf.ownEntry(f.entry_id)}
                                  />
                                </>
                              )}
                              {f.explanation && (
                                <>
                                  {DOT}
                                  <SecretValue value={f.explanation} secret={textSecret(f)} />
                                </>
                              )}
                            </div>
                            {f.suggested_fix && <FlagFix fix={f.suggested_fix} secret={textSecret(f)} />}
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
