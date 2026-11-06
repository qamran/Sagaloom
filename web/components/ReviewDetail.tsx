"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { CourseChip } from "@/components/CourseChip";
import { ReviewQueue } from "@/components/ReviewQueue";
import { getEntries } from "@/lib/api";
import { useAgentStream } from "@/lib/useAgentStream";
import { useWorld } from "@/lib/world";
import type { CheckResult, Decision, ImportNote, PendingInterrupt } from "@/lib/types";

const BTN = "min-h-11 rounded-lg px-4 text-[13px] disabled:opacity-50";
const BTN_PRIMARY = `${BTN} bg-accent font-semibold text-accent-foreground hover:brightness-110`;
const BTN_OUTLINE = `${BTN} border border-border-strong bg-transparent text-foreground hover:bg-panel-3`;
const LINK_BTN = `flex ${BTN} items-center no-underline hover:no-underline`;

const NOTHING_WAITING = "This conversation has nothing waiting for review.";
const NOTHING_IMPORTED = "Nothing from this import needs review.";

/** The candidates an import left out, each with why. Titles are the model's, shown as plain text. */
function NotImported({ note }: { note: ImportNote | null }) {
  if (!note || note.skipped.length === 0) return null;
  return (
    <section aria-label="Not imported" className="flex flex-col gap-2">
      <h2 className="m-0 text-xs font-semibold uppercase tracking-[1px] text-muted-foreground">Not imported</h2>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
        {note.skipped.map((k, i) => (
          <li key={i} className="rounded-[10px] border border-border bg-panel-2 px-3.5 py-2">
            <span className="font-semibold">{k.title}</span>
            <span className="text-muted-foreground"> · {k.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A pending set the author has not decided yet, with the choices made so far. */
interface Held {
  pending: PendingInterrupt;
  chosen: Record<string, Decision>;
}

/** One thread's pending proposals as a queue and the selected card, with one submit (spec §3.8). */
export function ReviewDetail({ threadId }: { threadId: string }) {
  const s = useAgentStream(threadId, { autoSubmit: false });
  const { world } = useWorld();
  const [selected, setSelected] = useState<string | null>(null);
  // How many review notes the thread had when the author submitted; later ones are this turn's.
  const [notesBefore, setNotesBefore] = useState<number | null>(null);
  // The hook clears `pending` the moment decisions are sent: keep showing the cards, disabled.
  const [held, setHeld] = useState<Held | null>(null);
  if (s.pending && (held?.pending !== s.pending || held.chosen !== s.chosen)) {
    setHeld({ pending: s.pending, chosen: s.chosen });
  }

  const busy = s.status === "streaming" || s.status === "reconnecting";
  const live = s.pending ?? (busy ? held?.pending : null) ?? null;
  // A proposal the server sent without a check counts as a failed one, so it still gets a row and a decision.
  const shown: PendingInterrupt | null = live && {
    ...live,
    checks: Object.fromEntries(
      live.proposals.map((p): [string, CheckResult] => [
        p.proposal_id,
        live.checks[p.proposal_id] ?? { proposal_id: p.proposal_id, verdict: "failed", flags: [], dependents: [], badge: "failed" },
      ]),
    ),
  };
  const chosen = s.pending ? s.chosen : (held?.chosen ?? {});
  const worldId = shown?.proposals[0]?.world_id ?? world?.id;
  const { data: canon } = useQuery({
    queryKey: ["entries", worldId],
    queryFn: () => getEntries(worldId as string),
    // Loaded up front so cited secrets can be identified; the queue and card fail closed until then.
    enabled: !!worldId,
  });

  const isImport = s.kind === "import";
  const back = (
    <Link href="/review" className={`${LINK_BTN} border border-border-strong text-foreground`}>
      Back to Review
    </Link>
  );
  const backToImport = (
    <Link href="/import" className={`${LINK_BTN} ${BTN_OUTLINE}`}>
      Back to Import
    </Link>
  );
  const page = (children: React.ReactNode) => <main className="flex flex-col gap-4 px-4 py-6 md:px-11">{children}</main>;

  if (!s.loaded) return page(<p className="m-0 text-muted-foreground">Loading…</p>);

  const otherWorld = !!s.worldId && !!world && s.worldId !== world.id;
  // A decided import has only this page for its outcome (no Open in Chat), so its notes show even
  // when nothing was submitted in this session (F7).
  const decided = isImport && s.messages.some((m) => m.role === "review");
  if (otherWorld || (!shown && notesBefore === null && !decided)) {
    return page(
      <>
        <p className="m-0 text-[17px] text-[#c9c6bd]">{isImport && !otherWorld ? NOTHING_IMPORTED : NOTHING_WAITING}</p>
        {isImport && !otherWorld && <NotImported note={s.importNote} />}
        <div className="flex flex-wrap gap-2.5">
          {back}
          {isImport && !otherWorld && backToImport}
        </div>
        {s.error && (
          <p role="alert" className="m-0 text-sm text-conflict">
            {s.error}
          </p>
        )}
      </>,
    );
  }

  if (!shown) {
    const notes = s.messages.filter((m) => m.role === "review").slice(notesBefore ?? 0);
    return page(
      <>
        <h1 className="m-0 font-heading text-[26px] font-medium">Review</h1>
        {notes.length > 0 && (
          <ul aria-label="Decision notes" className="m-0 flex list-none flex-col gap-2 p-0 text-sm">
            {notes.map((m, i) => (
              <li key={i} className="rounded-[10px] border border-border bg-panel-2 px-3.5 py-2.5">
                {m.content}
              </li>
            ))}
          </ul>
        )}
        {isImport && <NotImported note={s.importNote} />}
        {s.error && (
          <p role="alert" className="m-0 text-sm text-conflict">
            {s.error}
          </p>
        )}
        <div className="flex flex-wrap gap-2.5">
          {back}
          {isImport ? (
            backToImport
          ) : (
            <Link href={`/chat/${encodeURIComponent(threadId)}`} className={`${LINK_BTN} ${BTN_OUTLINE}`}>
              Open in Chat
            </Link>
          )}
        </div>
      </>,
    );
  }

  const proposals = shown.proposals;
  const current = proposals.find((p) => p.proposal_id === selected) ?? proposals[0];
  const n = proposals.length;
  const clean = proposals.filter((p) => {
    const c = shown.checks[p.proposal_id];
    return !chosen[p.proposal_id] && c.verdict === "none" && c.flags.length === 0 && p.action !== "delete";
  });
  const unchosen = proposals.filter((p) => !chosen[p.proposal_id]);
  const complete = n > 0 && proposals.every((p) => chosen[p.proposal_id]);
  const submit = () => {
    setNotesBefore(s.messages.filter((m) => m.role === "review").length);
    void s.decide(proposals.map((p) => chosen[p.proposal_id]));
  };

  return (
    <div className="flex min-h-0 flex-1 flex-wrap">
      <aside
        aria-label="Pending proposals"
        className="flex w-full shrink-0 flex-col gap-3.5 border-b border-border bg-panel px-4 py-5 md:w-[380px] md:border-b-0 md:border-r"
      >
        <h1 className="m-0 font-heading text-[26px] font-medium leading-[1.15]">Review</h1>
        <p className="m-0 text-[13px] text-muted-foreground">
          {n} {n === 1 ? "proposal" : "proposals"} · nothing enters canon until you decide
        </p>
        {shown.error && (
          <p role="alert" className="m-0 text-sm text-conflict">
            {shown.error}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {clean.length > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void s.chooseMany(clean.map((p) => ({ proposal_id: p.proposal_id, action: "approve" })))}
              className={BTN_PRIMARY}
            >
              Approve {clean.length} with no issues
            </button>
          )}
          <button
            type="button"
            disabled={busy || unchosen.length === 0}
            onClick={() => void s.chooseMany(unchosen.map((p) => ({ proposal_id: p.proposal_id, action: "reject" })))}
            className={BTN_OUTLINE}
          >
            Reject all
          </button>
        </div>
        <ReviewQueue
          pending={shown}
          canon={canon}
          selectedId={current?.proposal_id ?? ""}
          chosen={chosen}
          onSelect={setSelected}
        />
      </aside>

      <main className="flex min-w-0 flex-[999_1_520px] flex-col gap-4 px-4 py-6 md:px-10">
        {isImport && current && (
          <p className="m-0 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
            <span>
              From {s.importNote?.source ?? "paste"}
              {s.importNote?.first_lines[current.proposal_id] ? `: “${s.importNote.first_lines[current.proposal_id]}”` : ""}
            </span>
            <CourseChip card="injection_safe_extraction" label="Injection-safe extraction" />
          </p>
        )}
        {current && (
          <ApprovalCard
            key={current.proposal_id}
            proposal={current}
            check={shown.checks[current.proposal_id]}
            canon={canon}
            chosen={chosen[current.proposal_id]}
            onUndo={() => s.unchoose(current.proposal_id)}
            disabled={busy}
            onDecide={(d) => void s.choose(d)}
          />
        )}
        {busy && (
          <p role="status" className="m-0 text-sm text-muted-foreground">
            Sending your decisions…
          </p>
        )}
        {s.error && (
          <p role="alert" className="m-0 text-sm text-conflict">
            {s.error}
          </p>
        )}
        <div>
          <button type="button" disabled={!complete || busy} onClick={submit} className={BTN_PRIMARY}>
            Submit {n} {n === 1 ? "decision" : "decisions"}
          </button>
        </div>
        {isImport && <NotImported note={s.importNote} />}
      </main>
    </div>
  );
}
