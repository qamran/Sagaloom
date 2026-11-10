"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApprovalCard } from "@/components/ApprovalCard";
import { CourseChip } from "@/components/CourseChip";
import { ReviewQueue } from "@/components/ReviewQueue";
import { getEntries } from "@/lib/api";
import { entryIsSecret } from "@/lib/review";
import { SecretsWorldProvider, useWorldShowSecrets } from "@/lib/secrets";
import { entryIsNc, licenceText } from "@/lib/sources";
import { useAgentStream } from "@/lib/useAgentStream";
import { useWorld } from "@/lib/world";
import type { CheckResult, Entry, ImportNote, PendingInterrupt, Proposal } from "@/lib/types";

const BTN = "min-h-11 rounded-lg px-4 text-[13px] disabled:opacity-50";
const BTN_PRIMARY = `${BTN} bg-accent font-semibold text-accent-foreground hover:brightness-110`;
const BTN_OUTLINE = `${BTN} border border-border-strong bg-transparent text-foreground hover:bg-panel-3`;
const LINK_BTN = `flex ${BTN} items-center no-underline hover:no-underline`;

const NOTHING_WAITING = "This conversation has nothing waiting for review.";
const OTHER_WORLD = "This conversation belongs to another world. Switch worlds to review it.";
const NOTHING_IMPORTED = "Nothing from this import needs review.";
const nonCommercial = (licence: string) =>
  `Non-commercial licence. Some of these pages are licensed for non-commercial use only (${licence}). Approving them means this world can't be used commercially.`;

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
            {k.paste && (
              <>
                {" · "}
                <Link href="/import#paste" className="text-accent underline underline-offset-2">
                  Paste the text instead
                </Link>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The licence the thread's proposals are under, and a box that warns when any of them is non-commercial only. */
function LicenceNotice({ note, proposals }: { note: ImportNote | null; proposals: Proposal[] }) {
  const anyNc = proposals.some((p) => entryIsNc(p.after));
  const nc = proposals.flatMap((p) => p.after?.sources ?? []).find((s) => s.nc === true);
  return (
    <>
      {note?.kind === "wiki" && <p className="m-0 text-[13px]">Licence: {licenceText({ licence: note.licence?.text, licence_url: note.licence?.url })}</p>}
      {anyNc && (
        <p role="note" className="m-0 rounded-[10px] border border-conflict-line bg-conflict-bg px-3.5 py-2.5 text-[13px] text-conflict-text">
          {nonCommercial(licenceText({ licence: nc?.licence, licence_url: nc?.licence_url }))}
        </p>
      )}
    </>
  );
}

/** Where the selected card came from: the page URL of a wiki import (never for a hidden secret entry), or the first lines of pasted text. */
function ImportProvenance({ note, current, canon }: { note: ImportNote | null; current: Proposal; canon: Entry[] | undefined }) {
  const worldShown = useWorldShowSecrets();
  if (note?.kind === "wiki") {
    // The primary source is the page being imported; sources[0] can be an earlier reference.
    const url = current.after?.source_url ?? current.after?.sources?.[0]?.url;
    const hidden = entryIsSecret(current, canon) && !worldShown;
    return (
      <p className="m-0 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
        {url && !hidden && <span>From {url}</span>}
        <CourseChip card="official_canon_licence" label="Official canon · licence" />
      </p>
    );
  }
  return (
    <p className="m-0 flex flex-wrap items-center gap-x-2 text-[13px] text-muted-foreground">
      <span>
        From {note?.source ?? "paste"}
        {note?.first_lines[current.proposal_id] ? `: “${note.first_lines[current.proposal_id]}”` : ""}
      </span>
      <CourseChip card="injection_safe_extraction" label="Injection-safe extraction" />
    </p>
  );
}

function ErrorLine({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <p role="alert" className="m-0 text-sm text-conflict">
      {text}
    </p>
  );
}

/** One thread's pending proposals as a queue and the selected card, with one submit (spec §3.8). */
export function ReviewDetail({ threadId }: { threadId: string }) {
  const s = useAgentStream(threadId, { autoSubmit: false });
  const { world } = useWorld();
  const [selected, setSelected] = useState<string | null>(null);
  // How many review notes the thread had when the author submitted; later ones are this turn's.
  const [notesBefore, setNotesBefore] = useState<number | null>(null);

  const busy = s.status === "streaming" || s.status === "reconnecting";
  // The hook clears `pending` the moment decisions are sent: keep showing the cards, disabled.
  const live = s.pending ?? (busy ? s.sent?.pending : null) ?? null;
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
  const chosen = s.pending ? s.chosen : (s.sent?.chosen ?? {});
  const worldId = shown?.proposals[0]?.world_id ?? world?.id;
  const { data: canon } = useQuery({
    queryKey: ["entries", worldId],
    queryFn: () => getEntries(worldId as string),
    // Loaded up front so cited secrets can be identified; the queue and card fail closed until then.
    // A failed load keeps an update's or delete's own entry behind its one Show (Ruling 10).
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

  const otherWorld =
    !!world && ((!!s.worldId && s.worldId !== world.id) || (!!shown && shown.proposals.some((p) => p.world_id !== world.id)));
  // A decided import has only this page for its outcome (no Open in Chat), so its notes show even
  // when nothing was submitted in this session (F7).
  const decided = isImport && s.messages.some((m) => m.role === "review");
  if (otherWorld || (!shown && notesBefore === null && !decided)) {
    return page(
      <>
        <p className="m-0 text-[17px] text-prose-muted">{otherWorld ? OTHER_WORLD : isImport ? NOTHING_IMPORTED : NOTHING_WAITING}</p>
        {isImport && !otherWorld && <NotImported note={s.importNote} />}
        <div className="flex flex-wrap gap-2.5">
          {back}
          {isImport && !otherWorld && backToImport}
        </div>
        <ErrorLine text={s.error} />
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
        <ErrorLine text={s.error} />
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

  // The queue and the card follow the thread's world's toggle ("" fails closed: nothing shows).
  return (
    <SecretsWorldProvider worldId={worldId ?? ""}>
      <div className="flex min-h-0 flex-1 flex-wrap">
        <aside
          aria-label="Pending proposals"
          className="flex w-full shrink-0 flex-col gap-3.5 border-b border-border bg-panel px-4 py-5 md:w-[380px] md:border-b-0 md:border-r"
        >
          <h1 className="m-0 font-heading text-[26px] font-medium leading-[1.15]">Review</h1>
          <p className="m-0 text-[13px] text-muted-foreground">
            {n} {n === 1 ? "proposal" : "proposals"} · nothing enters canon until you decide
          </p>
          <ErrorLine text={shown.error} />
          <LicenceNotice note={isImport ? s.importNote : null} proposals={proposals} />
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
          {isImport && current && <ImportProvenance note={s.importNote} current={current} canon={canon} />}
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
          <ErrorLine text={s.error} />
          <div>
            <button type="button" disabled={!complete || busy} onClick={submit} className={BTN_PRIMARY}>
              Submit {n} {n === 1 ? "decision" : "decisions"}
            </button>
          </div>
          {isImport && <NotImported note={s.importNote} />}
        </main>
      </div>
    </SecretsWorldProvider>
  );
}
