"use client";

import { Component, useState, type ReactNode } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { EYEBROW, H2, LEDE, WRAP } from "@/components/home/styles";
import { TYPE_CHIP, TYPE_DOT, TYPE_LABEL } from "@/lib/entity";
import type { Entry, PublicPreview } from "@/lib/types";

/** The entry the recorded card cites, opened first so the clash can be read from both sides. */
const CITED = "ent_0012";
const noop = () => {};
const UNAVAILABLE = <p className="m-0 mt-8 text-muted-foreground">Preview unavailable right now.</p>;

/** Data the card cannot render must not take the home page down: the section says unavailable instead. */
class PreviewBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/**
 * The recorded Velmar example (M5 §5.7 item 3): the author's message, the real ApprovalCard in its
 * read-only mode, and a few entries to open and read. All from props; nothing here fetches.
 */
export function Preview({ preview }: { preview: PublicPreview | null }) {
  return (
    <section aria-labelledby="home-preview" className="border-t border-border bg-panel py-16 sm:py-20">
      <div className={WRAP}>
        <p className={EYEBROW}>Preview</p>
        <h2 id="home-preview" className={H2}>
          See it catch a contradiction
        </h2>
        <p className={LEDE}>
          A recorded example from Velmar, the sample world every new account starts with. Nothing on this page calls a
          model or changes anything.
        </p>
        {preview ? (
          <PreviewBoundary fallback={UNAVAILABLE}>
            <Recorded preview={preview} />
          </PreviewBoundary>
        ) : (
          UNAVAILABLE
        )}
      </div>
    </section>
  );
}

function Recorded({ preview }: { preview: PublicPreview }) {
  const { messages, pending_interrupt: pending, entries } = preview;
  return (
    <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex flex-col gap-3">
          {messages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m, i) =>
              m.role === "user" ? (
                <div
                  key={i}
                  className="max-w-[85%] self-end whitespace-pre-wrap rounded-[14px_14px_4px_14px] border border-user-line bg-panel-3 px-4 py-3 font-heading text-base"
                >
                  <span className="sr-only">The author: </span>
                  {m.content}
                </div>
              ) : (
                <div key={i} className="max-w-[85%] whitespace-pre-wrap text-prose">
                  <span className="sr-only">Sagaloom: </span>
                  {m.content}
                </div>
              ),
            )}
        </div>
        {pending.proposals.map((p) => {
          const check = pending.checks[p.proposal_id];
          return check ? (
            <ApprovalCard key={p.proposal_id} proposal={p} check={check} canon={entries} onDecide={noop} readOnly />
          ) : null;
        })}
      </div>
      <Entries entries={entries} />
    </div>
  );
}

function Entries({ entries }: { entries: Entry[] }) {
  const [openId, setOpenId] = useState(() => (entries.some((e) => e.id === CITED) ? CITED : entries[0]?.id));
  const open = entries.find((e) => e.id === openId);
  if (entries.length === 0) return null;
  return (
    <section aria-labelledby="home-entries" className="flex min-w-0 flex-col gap-3 self-start rounded-[14px] border border-border bg-panel-2 p-4">
      <h3 id="home-entries" className="m-0 font-heading text-[17px] font-semibold">
        Velmar entries
      </h3>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {entries.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              aria-pressed={e.id === openId}
              onClick={() => setOpenId(e.id)}
              className={`flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm sm:min-h-9 ${
                e.id === openId ? "bg-row-active text-foreground" : "text-prose-muted hover:bg-panel-3"
              }`}
            >
              <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${TYPE_DOT[e.type]}`} />
              <span className="flex-1">{e.title}</span>
              <span className="text-xs text-muted-foreground">{TYPE_LABEL[e.type]}</span>
            </button>
          </li>
        ))}
      </ul>
      {open && <EntryReader entry={open} entries={entries} onOpen={setOpenId} />}
    </section>
  );
}

/** One entry, read-only: what the Canon page shows, minus everything that needs an account. */
function EntryReader({ entry, entries, onOpen }: { entry: Entry; entries: Entry[]; onOpen: (id: string) => void }) {
  return (
    <article aria-labelledby={`home-entry-${entry.id}`} className="flex flex-col gap-3 border-t border-border pt-3">
      <div>
        <div className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">
          {TYPE_LABEL[entry.type]} · {entry.status} · {entry.id}
        </div>
        <h4 id={`home-entry-${entry.id}`} className="m-0 mt-0.5 font-heading text-xl font-semibold">
          {entry.title}
        </h4>
      </div>
      <p className="m-0 whitespace-pre-line font-heading text-[15px] leading-relaxed text-prose">{entry.body}</p>
      {entry.facts.length > 0 && (
        <dl className="m-0 flex flex-col gap-2.5">
          {entry.facts.map((f, i) => (
            <div key={`${f.key}-${i}`}>
              <dt className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">{f.key}</dt>
              <dd className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <span>{f.value}</span>
                {f.refs.map((id) => (
                  <Ref key={id} id={id} entries={entries} onOpen={onOpen} />
                ))}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  );
}

/** An entry a fact points at: opens it when the preview holds it, otherwise just its ID (never a link). */
function Ref({ id, entries, onOpen }: { id: string; entries: Entry[]; onOpen: (id: string) => void }) {
  const target = entries.find((e) => e.id === id);
  if (!target) return <span className="text-xs text-muted-foreground">{id}</span>;
  return (
    <button
      type="button"
      onClick={() => onOpen(id)}
      className={`inline-flex min-h-11 items-center rounded-md border px-2 py-0.5 text-[13px] hover:brightness-125 sm:min-h-0 ${TYPE_CHIP[target.type]}`}
    >
      <span className="sr-only">Open </span>
      {target.title}
    </button>
  );
}
