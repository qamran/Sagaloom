"use client";

import { useState, type FormEvent } from "react";
import { CourseChip } from "@/components/CourseChip";
import { EntityChip } from "@/components/EntityChip";
import { FactList } from "@/components/FactList";
import { BodyDiff, LineDiff } from "@/components/DiffView";
import { Cite, FactTable, FlagFix, KIND_LABEL, SecretValue, type SecretOf } from "@/components/FactTable";
import { TYPE_LABEL } from "@/lib/entity";
import { buildFactRows, lineDiff } from "@/lib/factRows";
import { SecretsWorldProvider, useWorldShowSecrets } from "@/lib/secrets";
import { entryIsNc, isHttpsUrl, licenceText } from "@/lib/sources";
import {
  BADGE_CLASS,
  BADGE_LABEL,
  badgeOf,
  CHECK_FAILED_TEXT,
  entryIndex,
  isSecretFact,
  judgeSecrets,
} from "@/lib/review";
import type { Badge, CheckResult, Decision, Entry, EntryDraft, EntryType, Fact, Proposal, Status } from "@/lib/types";

const TEXTAREA =
  "w-full rounded-lg border border-border bg-background px-3 py-2 font-heading text-[15px] text-foreground";
const HIDDEN_ENTRY = "Secret entry: hidden";
const STATUSES: Status[] = ["canon", "myth", "rumour", "secret"];
const ACTION_LABEL: Record<Proposal["action"], string> = { create: "New entry", update: "Update", delete: "Delete" };
const DECISION_LABEL: Record<Decision["action"], string> = {
  approve: "Approve",
  edit: "Edit",
  reject: "Reject",
  save_as_myth: "Save as myth",
};

const BTN = "min-h-11 rounded-lg px-4 text-[13px] disabled:opacity-50";
const BTN_PRIMARY = `${BTN} bg-accent font-semibold text-accent-foreground hover:brightness-110`;
const BTN_SECONDARY = `${BTN} border border-border-strong bg-transparent text-foreground hover:bg-panel-3`;
const BTN_REJECT = `${BTN} border border-conflict-line bg-transparent text-conflict-text hover:bg-conflict-bg`;
const BADGE = "rounded-full px-2.5 py-0.5 text-xs font-semibold";
const INPUT =
  "min-h-11 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground sm:min-h-9";

interface Props {
  proposal: Proposal;
  check: CheckResult;
  onDecide: (d: Decision) => void;
  /** Entries of this world, used to colour citations by type and to hide cited secrets. */
  canon?: Entry[];
  /** This card's decision while others in the same interrupt are still open. */
  chosen?: Decision;
  onUndo?: () => void;
  disabled?: boolean;
}

/** "Commit to canon?" (R5.2, R5.3, R5.6, R12.3): one proposal as a card; its secrets follow the proposal's own world's toggle. */
export function ApprovalCard(props: Props) {
  return (
    <SecretsWorldProvider worldId={props.proposal.world_id}>
      <ApprovalCardBody {...props} />
    </SecretsWorldProvider>
  );
}

function ApprovalCardBody({ proposal, check, onDecide, canon, chosen, onUndo, disabled }: Props) {
  const [editing, setEditing] = useState(false);
  const [toldBy, setToldBy] = useState("");
  const [entryRevealed, setEntryRevealed] = useState(false);
  const worldShown = useWorldShowSecrets();
  const pid = proposal.proposal_id;
  // A secret entry is hidden on the card, title, body and facts (R12.12, ruling R8). Either side
  // counts, as in the line diff, so an update that un-secrets an entry stays masked until approved,
  // and so does the entry as stored now (it may have turned secret after this proposal was drafted).
  // The header's Show is the one reveal for everything hidden for the entry's sake.
  const judged = judgeSecrets(proposal, canon, "open");
  const entrySecret = judged.entrySecret;
  const entryHidden = entrySecret && !worldShown && !entryRevealed;

  // Fail closed: until this world's entries have loaded, any other entry cited by a flag may be
  // secret, so its title, value and quotes stay hidden behind Show (R12.12).
  const { byId, unknown } = entryIndex(proposal, canon);
  const typeOf = (id: string): EntryType | undefined =>
    byId.get(id)?.type ?? check.dependents.find((d) => d.id === id)?.type ??
    (id && id === proposal.entry_id ? (proposal.after?.type ?? proposal.before?.type) : undefined);
  const ownEntry = (id: string) => !!id && id === proposal.entry_id;
  // A flag citing this entry itself (a retcon) is hidden with the entry and has no Show of its own.
  const citeSecret = (id: string) => (ownEntry(id) ? entryHidden : unknown(id) || byId.get(id)?.status === "secret");

  // Everything of this entry's own is judged as if the entry were not secret (`judgeSecrets` "open"):
  // `entryHidden` covers that part (one mask, the header's one Show), and what is left is secret in
  // its own right, each value behind its own Show.
  const existingSecret = judged.existing;
  // The existing side of a flag, and the judge's free text about it (explanation, suggested
  // fix), may restate a secret: the server marks such flags (existing_secret), and the client
  // heuristics in lib/review.ts still apply on top.
  const textSecret = judged.text;

  const badge = badgeOf(check);
  const failed = badge === "failed";
  const flags = check.flags;
  const conflict = badge === "conflict" || badge === "possible";
  const retcon = flags.some((f) => f.kind === "retcon");
  const note = flags.some((f) => f.kind === "note");
  // The worst badge first, then Retcon and Note when flags of that kind sit under a worse one.
  const badges: Badge[] = [badge];
  if (retcon && badge !== "retcon") badges.push("retcon");
  if (note && !failed && badge !== "note") badges.push("note");
  const shownBadges = badges.filter((b) => b !== "clear" || proposal.action !== "delete");
  const canMyth = proposal.after !== null && !failed && (conflict || retcon);
  const approveLabel = conflict || retcon || failed ? "Approve anyway" : "Approve";

  // On a failed check the notice flag (no fact, no quotes) repeats the warning above: drop it.
  const shown = failed
    ? flags.filter((f) => !(f.kind === "note" && !f.fact_key && !f.existing_quote && !f.new_quote))
    : flags;
  const rows = buildFactRows(proposal, { ...check, flags: shown });
  const before = proposal.action === "update" ? proposal.before : null;
  const after = proposal.after;
  const prose = shown.filter((f) => !f.fact_key);
  const proseSecret = judged.prose;
  const draftSecret = judged.draft;
  // Prose about a flag can restate this entry's facts: hidden with the entry, no Show of its own.
  // A quote from another entry is that entry's text and keeps its own rule.
  const withEntry = (secret: boolean) => ({ secret: entryHidden || secret, revealable: !entryHidden });
  const secretOf: SecretOf = {
    entry: entryHidden,
    canon: (f) => f.status === "secret",
    proposed: (f) => f.status === "secret",
    existing: existingSecret,
    incoming: (f) => isSecretFact(judged.proposal.after, f.fact_key, f.new_fact),
    text: textSecret,
    cite: citeSecret,
    ownEntry,
  };

  const tone =
    conflict || failed
      ? { box: "border-conflict-line", head: "bg-conflict-bg border-conflict-line" }
      : retcon
        ? { box: "border-event-line", head: "bg-event-bg border-event-line" }
        : { box: "border-border", head: "bg-panel-3 border-border" };

  const title = proposal.after?.title ?? proposal.before?.title ?? "Untitled";
  const shownTitle = entryHidden ? "Secret entry" : title;
  const dependentSecret = (id: string) => !worldShown && (unknown(id) || byId.get(id)?.status === "secret");
  const type = proposal.after?.type ?? proposal.before?.type;
  const version =
    proposal.action === "update" && proposal.before ? ` · v${proposal.before.version} → v${proposal.before.version + 1}` : "";

  const decide = (action: Decision["action"]) => {
    if (action === "save_as_myth" && toldBy.trim()) onDecide({ proposal_id: pid, action, told_by: toldBy.trim() });
    else onDecide({ proposal_id: pid, action });
  };

  return (
    <section aria-label={`Review proposal: ${entryHidden ? "secret entry" : title}`} className={`overflow-hidden rounded-[14px] border bg-panel-2 ${tone.box}`}>
      <div className={`flex flex-wrap items-center gap-2.5 border-b px-[18px] py-3 ${tone.head}`}>
        <ul aria-label="Check result" className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {shownBadges.map((b) => (
            <li key={b} className={`${BADGE} ${BADGE_CLASS[b]}`}>
              {b === "clear" ? "No conflicts found" : BADGE_LABEL[b]}
            </li>
          ))}
        </ul>
        <h3 className="m-0 font-heading text-[17px] font-semibold">Commit to canon?</h3>
        <CourseChip card="human_in_the_loop" label="Human-in-the-loop · interrupt()" />
        <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground sm:ml-auto">
          {ACTION_LABEL[proposal.action]} ·{" "}
          {type ? <EntityChip type={type} name={shownTitle} /> : <span className="text-foreground">{shownTitle}</span>}
          {entryHidden && (
            <button
              type="button"
              onClick={() => setEntryRevealed(true)}
              aria-label="Show secret entry"
              className="min-h-11 rounded-md border border-border-strong px-3 text-xs text-foreground hover:bg-panel-3 sm:min-h-8"
            >
              Show
            </button>
          )}
          {proposal.entry_id && <> · {proposal.entry_id}</>}
          {version}
        </span>
      </div>

      <div className="flex flex-col gap-3.5 px-[18px] py-4">
        {failed && (
          <p role="alert" className="m-0 rounded-[10px] border border-conflict-line bg-conflict-bg px-3.5 py-3 text-sm text-conflict-text">
            {CHECK_FAILED_TEXT}
          </p>
        )}

        {before && after && (
          <>
            <LineDiff changes={lineDiff(before, after)} secret={entryHidden} revealable={false} />
            <BodyDiff before={before.body} after={after.body} secret={entryHidden} revealable={false} />
          </>
        )}

        <FactTable rows={rows} secretOf={secretOf} typeOf={typeOf} />

        {prose.map((f, i) => (
          <div key={`${f.kind}-${f.entry_id}-${i}`} className="flex flex-col gap-1 text-[13px] text-prose-muted">
            <div className="flex flex-wrap items-center gap-1.5">
              <strong className="text-foreground">{KIND_LABEL[f.kind]}</strong>
              <span aria-hidden="true">·</span>
              <Cite
                id={f.entry_id}
                title={f.title}
                type={typeOf(f.entry_id)}
                secret={citeSecret(f.entry_id)}
                revealable={!ownEntry(f.entry_id)}
              />
              {f.explanation && <SecretValue value={f.explanation} {...withEntry(proseSecret(f))} />}
            </div>
            {f.existing_quote && (
              <blockquote className="m-0 border-l-2 border-border-strong pl-3 font-heading text-[15px]">
                In canon: “
                <SecretValue
                  value={f.existing_quote}
                  {...(ownEntry(f.entry_id) ? withEntry(textSecret(f)) : { secret: textSecret(f) })}
                />”
              </blockquote>
            )}
            {f.new_quote && (
              <blockquote className="m-0 border-l-2 border-conflict/60 pl-3 font-heading text-[15px]">
                Proposed: “
                <SecretValue value={f.new_quote} {...withEntry(draftSecret)} />”
              </blockquote>
            )}
            {f.suggested_fix && <FlagFix fix={f.suggested_fix} {...withEntry(proseSecret(f))} />}
          </div>
        ))}

        {before && after ? (
          !entryHidden && <SourceLine draft={after} />
        ) : proposal.after ? (
          <div className="flex flex-col gap-3 rounded-[10px] border border-border px-3.5 py-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">
                {type ? TYPE_LABEL[type] : "Entry"} · {proposal.after.status}
              </div>
              <div className="font-heading text-lg font-semibold">
                <SecretValue value={proposal.after.title} secret={entryHidden} revealable={false} />
              </div>
              {!entryHidden && <SourceLine draft={proposal.after} />}
              {proposal.after.body && (
                <p className="m-0 mt-1 line-clamp-4 whitespace-pre-line font-heading text-[15px] text-prose">
                  <SecretValue value={proposal.after.body} secret={entryHidden} revealable={false} />
                </p>
              )}
            </div>
            <section aria-label="Drafted facts" className="flex flex-col gap-2">
              <h4 className="m-0 text-xs font-semibold uppercase tracking-[1px]">Facts to commit</h4>
              <FactList facts={proposal.after.facts} entries={canon} hideAll={entryHidden} />
            </section>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded-[10px] border border-border px-3.5 py-3 text-[13px]">
            <div>This entry will be deleted from canon.</div>
            <DeleteDependents dependents={check.dependents} worldShown={worldShown} secret={dependentSecret} />
          </div>
        )}

        {chosen ? (
          <div className="flex flex-wrap items-center gap-3 text-[13px]">
            <span>
              Your choice: <strong>{DECISION_LABEL[chosen.action]}</strong>. Waiting for the other changes.
            </span>
            {onUndo && (
              <button type="button" onClick={onUndo} disabled={disabled} className={BTN_SECONDARY}>
                Change
              </button>
            )}
          </div>
        ) : editing && proposal.after ? (
          <EditForm
            draft={proposal.after}
            secretEntry={entrySecret}
            disabled={disabled}
            onCancel={() => setEditing(false)}
            onSubmit={(edited) => onDecide({ proposal_id: pid, action: "edit", edited })}
          />
        ) : (
          <div className="flex flex-col gap-2.5">
            {canMyth && (
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor={`told-by-${pid}`} className="text-xs text-muted-foreground">
                  Told by (optional)
                </label>
                <input
                  id={`told-by-${pid}`}
                  value={toldBy}
                  onChange={(e) => setToldBy(e.target.value)}
                  placeholder="e.g. The Ashen Choir"
                  maxLength={120}
                  className={`${INPUT} max-w-60`}
                />
              </div>
            )}
            <div className="flex flex-wrap gap-2.5">
              {canMyth && (
                <button type="button" disabled={disabled} onClick={() => decide("save_as_myth")} className={BTN_PRIMARY}>
                  Save as myth
                </button>
              )}
              {proposal.action !== "delete" && (
                <button type="button" disabled={disabled} onClick={() => setEditing(true)} className={BTN_SECONDARY}>
                  Edit
                </button>
              )}
              <button
                type="button"
                disabled={disabled}
                onClick={() => decide("approve")}
                className={canMyth || failed ? BTN_SECONDARY : BTN_PRIMARY}
              >
                {approveLabel}
              </button>
              <button type="button" disabled={disabled} onClick={() => decide("reject")} className={`${BTN_REJECT} sm:ml-auto`}>
                Reject
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

const linkedCount = (n: number) => (n === 1 ? "1 linked entry" : `${n} linked entries`);

/**
 * What a delete touches: entries naming it in their text, then entries tied to it only by a link,
 * each under its own line. A link may be secret (the Mayor's to the Choir), so while the world
 * hides secrets link-only entries are a count only: no title, ID, type or link.
 */
function DeleteDependents({
  dependents,
  worldShown,
  secret,
}: {
  dependents: CheckResult["dependents"];
  worldShown: boolean;
  secret: (id: string) => boolean;
}) {
  const text = dependents.filter((d) => d.via !== "link");
  const linked = worldShown ? dependents.filter((d) => d.via === "link") : [];
  const counted = worldShown ? 0 : dependents.length - text.length;
  if (text.length === 0 && linked.length === 0 && counted === 0)
    return <div className="text-muted-foreground">No other entries mention it.</div>;
  if (text.length === 0 && linked.length === 0)
    return (
      <div className="text-muted-foreground">
        {linkedCount(counted)} {counted === 1 ? "depends" : "depend"} on it
      </div>
    );
  const chips = (list: CheckResult["dependents"]) =>
    list.map((d) =>
      secret(d.id) ? (
        <EntityChip key={d.id} type={d.type} name="Secret entry" />
      ) : (
        <span key={d.id} className="inline-flex items-center gap-1.5">
          <EntityChip type={d.type} name={d.title} href={`/canon/${encodeURIComponent(d.id)}`} />
          <span className="text-xs text-muted-foreground">{d.id}</span>
        </span>
      ),
    );
  return (
    <>
      {text.length > 0 && (
        <>
          <div className="text-muted-foreground">These entries mention it:</div>
          <div className="flex flex-wrap items-center gap-1.5">
            {chips(text)}
            {counted > 0 && <span className="text-muted-foreground">and {linkedCount(counted)}</span>}
          </div>
        </>
      )}
      {linked.length > 0 && (
        <>
          <div className="text-muted-foreground">These entries link to it:</div>
          <div className="flex flex-wrap items-center gap-1.5">{chips(linked)}</div>
        </>
      )}
    </>
  );
}

/** Where a reference or official draft came from: its kind, page URL and licence, with NC when any source is non-commercial. */
function SourceLine({ draft }: { draft: EntryDraft }) {
  if (draft.source !== "reference" && draft.source !== "official") return null;
  const url = draft.source_url ?? draft.sources?.[0]?.url;
  const primary = draft.sources?.find((s) => s.url === url) ?? draft.sources?.[0];
  const licence = licenceText({ licence: draft.licence ?? primary?.licence, licence_url: primary?.licence_url });
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <span>{draft.source === "reference" ? "Source: reference (Wikipedia)" : "Source: official (fan wiki)"}</span>
      {isHttpsUrl(url) && (
        <a href={url} target="_blank" rel="noopener noreferrer" className="break-all text-accent underline underline-offset-2">
          {url}
        </a>
      )}
      <span>
        Licence: {licence}
        {entryIsNc(draft) && " · NC"}
      </span>
    </div>
  );
}

function EditForm({
  draft,
  secretEntry,
  disabled,
  onCancel,
  onSubmit,
}: {
  draft: EntryDraft;
  /** The draft or the proposal's stored entry is secret: its title and body stay hidden until Show. */
  secretEntry: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSubmit: (edited: EntryDraft) => void;
}) {
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [facts, setFacts] = useState<Fact[]>(draft.facts);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [entryShown, setEntryShown] = useState(false);
  const worldShown = useWorldShowSecrets();
  // Hidden fields are never bound to the draft's text, so it is not in the DOM; submitting without
  // Show sends the draft's own title and body (the state below is never edited while hidden).
  const entryHidden = (secretEntry || draft.status === "secret") && !worldShown && !entryShown;
  // A fact row is hidden for the entry's sake until Show to edit, or for its own until its Show.
  // A hidden row's inputs are disabled, so it still holds exactly what was drafted.
  const rowHidden = (f: Fact, i: number) => !worldShown && !revealed.has(i) && (f.status === "secret" || entryHidden);

  const setFact = (i: number, patch: Partial<Fact>) =>
    setFacts((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      ...draft,
      title: title.trim() || draft.title,
      body,
      // A never-revealed row goes back as drafted (no trim, no empty-row filter): the author has
      // not seen it, so the form must not change it. Visible rows are trimmed, and blank ones dropped.
      facts: facts.flatMap((f, i) => {
        if (rowHidden(f, i)) return [f];
        const key = f.key.trim();
        const value = f.value.trim();
        return key && value ? [{ ...f, key, value }] : [];
      }),
    });
  }

  return (
    <form onSubmit={submit} aria-label="Edit proposal" className="flex flex-col gap-3 rounded-[10px] border border-border-strong px-3.5 py-3">
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Title
        {entryHidden ? (
          <input disabled value="" placeholder={HIDDEN_ENTRY} maxLength={120} className={INPUT} />
        ) : (
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} className={INPUT} />
        )}
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Body
        {entryHidden ? (
          <textarea disabled value="" placeholder={HIDDEN_ENTRY} rows={4} maxLength={4000} className={TEXTAREA} />
        ) : (
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} maxLength={4000} className={TEXTAREA} />
        )}
      </label>
      {entryHidden && (
        <button
          type="button"
          onClick={() => setEntryShown(true)}
          aria-label="Show secret entry to edit"
          className={`${BTN_SECONDARY} self-start`}
        >
          Show to edit
        </button>
      )}
      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-xs font-semibold uppercase tracking-[1px]">Facts</legend>
        {facts.map((f, i) => {
          const n = i + 1;
          const hide = rowHidden(f, i);
          return (
            <div key={i} className="flex flex-wrap items-center gap-2">
              {hide ? (
                // Like the title: a hidden key and value are not bound to their text, so neither is in the DOM.
                <>
                  <input aria-label={`Fact ${n} key`} disabled value="" maxLength={40} placeholder="Secret fact" className={`${INPUT} flex-[1_1_120px]`} />
                  <input aria-label={`Fact ${n} value`} disabled value="" maxLength={200} placeholder="Secret fact" className={`${INPUT} flex-[2_1_180px]`} />
                </>
              ) : (
                <>
                  <input aria-label={`Fact ${n} key`} value={f.key} onChange={(e) => setFact(i, { key: e.target.value })} maxLength={40} placeholder="Key" className={`${INPUT} flex-[1_1_120px]`} />
                  <input
                    aria-label={`Fact ${n} value`}
                    value={f.value}
                    onChange={(e) => setFact(i, { value: e.target.value })}
                    maxLength={200}
                    placeholder="Value"
                    className={`${INPUT} flex-[2_1_180px]`}
                  />
                </>
              )}
              {hide && (
                <button type="button" onClick={() => setRevealed((s) => new Set(s).add(i))} aria-label={`Show secret fact ${n}`} className={BTN_SECONDARY}>
                  Show
                </button>
              )}
              <select
                aria-label={`Fact ${n} status`}
                disabled={hide}
                value={f.status}
                onChange={(e) => setFact(i, { status: e.target.value as Status })}
                className={`${INPUT} w-auto`}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  setFacts((fs) => fs.filter((_, j) => j !== i));
                  setRevealed(new Set()); // rows shift: never carry a reveal to another fact
                }}
                aria-label={`Remove fact ${n}`} className={BTN_SECONDARY}>
                Remove
              </button>
            </div>
          );
        })}
        <button
          type="button"
          onClick={() => setFacts((fs) => [...fs, { key: "", value: "", refs: [], status: "canon", told_by: null }])}
          className={`${BTN_SECONDARY} self-start`}
        >
          Add fact
        </button>
      </fieldset>
      <div className="flex flex-wrap gap-2.5">
        <button type="submit" disabled={disabled} className={BTN_PRIMARY}>
          Submit edit
        </button>
        <button type="button" onClick={onCancel} className={BTN_SECONDARY}>
          Cancel
        </button>
      </div>
    </form>
  );
}
