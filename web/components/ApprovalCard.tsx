"use client";

import { useState, type FormEvent } from "react";
import { CourseChip } from "@/components/CourseChip";
import { EntityChip } from "@/components/EntityChip";
import { FactList } from "@/components/FactList";
import { BodyDiff, LineDiff } from "@/components/DiffView";
import { Cite, FactTable, FlagFix, KIND_LABEL, SecretValue, type SecretOf } from "@/components/FactTable";
import { TYPE_LABEL } from "@/lib/entity";
import { buildFactRows, lineDiff } from "@/lib/factRows";
import { BADGE_CLASS, BADGE_LABEL, badgeOf, existingSecretOf, isSecretFact } from "@/lib/review";
import type { Badge, CheckResult, Decision, Entry, EntryDraft, EntryType, Fact, Flag, Proposal, Status } from "@/lib/types";

export const CHECK_FAILED_TEXT =
  "The contradiction check couldn't run. Review this change yourself before approving.";

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
const BTN_REJECT = `${BTN} border border-[#5a4228] bg-transparent text-[#f0b98a] hover:bg-[#221c15]`;
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

/** "Commit to canon?" (R5.2, R5.3, R5.6, R12.3). */
export function ApprovalCard({ proposal, check, onDecide, canon, chosen, onUndo, disabled }: Props) {
  const [editing, setEditing] = useState(false);
  const [toldBy, setToldBy] = useState("");
  const pid = proposal.proposal_id;

  const byId = new Map<string, Pick<Entry, "status" | "facts" | "type" | "title">>();
  for (const e of canon ?? []) byId.set(e.id, e);
  if (proposal.before) byId.set(proposal.before.id, proposal.before);
  const typeOf = (id: string): EntryType | undefined =>
    byId.get(id)?.type ?? check.dependents.find((d) => d.id === id)?.type ??
    (id && id === proposal.entry_id ? (proposal.after?.type ?? proposal.before?.type) : undefined);
  // Fail closed: until this world's entries have loaded, any other entry cited by a flag may be
  // secret, so its title, value and quotes stay hidden behind Show (R12.12).
  const canonLoaded = canon !== undefined;
  const unknown = (id: string) => !!id && id !== proposal.entry_id && !canonLoaded;
  const citeSecret = (id: string) =>
    unknown(id) || (id !== proposal.entry_id && byId.get(id)?.status === "secret");
  const existingSecret = existingSecretOf(proposal, canon);
  // A quote can come from a secret fact's text, so mask it if the entry holds any secret.
  const quoteSecret = (id: string) => {
    if (unknown(id)) return true;
    const e = byId.get(id);
    return !!e && (e.status === "secret" || e.facts.some((x) => x.status === "secret"));
  };

  // The existing side of a flag, and the judge's free text about it (explanation, suggested
  // fix), may restate a secret: the server marks such flags (existing_secret), and the client
  // heuristics above still apply on top.
  const textSecret = (f: Flag) => (f.fact_key ? existingSecret(f) : f.existing_secret || quoteSecret(f.entry_id));

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
  // Prose about a flag can quote either side: the draft side counts as secret when the draft is a
  // secret entry or holds any secret fact (the mirror of quoteSecret for the existing side).
  const draftHoldsSecret = !!after && (after.status === "secret" || after.facts.some((x) => x.status === "secret"));
  const proseSecret = (f: Flag) => textSecret(f) || draftHoldsSecret;
  const ownSecret = (e: { status: Status } | null, f: Fact) => f.status === "secret" || e?.status === "secret";
  const secretOf: SecretOf = {
    canon: (f) => ownSecret(before, f),
    proposed: (f) => ownSecret(after, f),
    existing: existingSecret,
    incoming: (f) => isSecretFact(after, f.fact_key, f.new_fact),
    text: textSecret,
    cite: citeSecret,
  };

  const tone =
    conflict || failed
      ? { box: "border-[#5a4228]", head: "bg-[#221c15] border-[#5a4228]" }
      : retcon
        ? { box: "border-event-line", head: "bg-event-bg border-event-line" }
        : { box: "border-border", head: "bg-panel-3 border-border" };

  const title = proposal.after?.title ?? proposal.before?.title ?? "Untitled";
  const type = proposal.after?.type ?? proposal.before?.type;
  const version =
    proposal.action === "update" && proposal.before ? ` · v${proposal.before.version} → v${proposal.before.version + 1}` : "";

  const decide = (action: Decision["action"]) => {
    if (action === "save_as_myth" && toldBy.trim()) onDecide({ proposal_id: pid, action, told_by: toldBy.trim() });
    else onDecide({ proposal_id: pid, action });
  };

  return (
    <section aria-label={`Review proposal: ${title}`} className={`overflow-hidden rounded-[14px] border bg-panel-2 ${tone.box}`}>
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
          {type ? <EntityChip type={type} name={title} /> : <span className="text-foreground">{title}</span>}
          {proposal.entry_id && <> · {proposal.entry_id}</>}
          {version}
        </span>
      </div>

      <div className="flex flex-col gap-3.5 px-[18px] py-4">
        {failed && (
          <p role="alert" className="m-0 rounded-[10px] border border-[#5a4228] bg-[#221c15] px-3.5 py-3 text-sm text-[#f0b98a]">
            {CHECK_FAILED_TEXT}
          </p>
        )}

        {before && after && (
          <>
            <LineDiff changes={lineDiff(before, after)} />
            <BodyDiff
              before={before.body}
              after={after.body}
              secret={before.status === "secret" || after.status === "secret"}
            />
          </>
        )}

        <FactTable rows={rows} secretOf={secretOf} typeOf={typeOf} />

        {prose.map((f, i) => (
          <div key={`${f.kind}-${f.entry_id}-${i}`} className="flex flex-col gap-1 text-[13px] text-[#c9c6bd]">
            <div className="flex flex-wrap items-center gap-1.5">
              <strong className="text-foreground">{KIND_LABEL[f.kind]}</strong>
              <span aria-hidden="true">·</span>
              <Cite id={f.entry_id} title={f.title} type={typeOf(f.entry_id)} secret={citeSecret(f.entry_id)} />
              {f.explanation && <SecretValue value={f.explanation} secret={proseSecret(f)} />}
            </div>
            {f.existing_quote && (
              <blockquote className="m-0 border-l-2 border-border-strong pl-3 font-heading text-[15px]">
                In canon: “
                <SecretValue value={f.existing_quote} secret={textSecret(f)} />”
              </blockquote>
            )}
            {f.new_quote && (
              <blockquote className="m-0 border-l-2 border-conflict/60 pl-3 font-heading text-[15px]">
                Proposed: “
                <SecretValue value={f.new_quote} secret={draftHoldsSecret} />”
              </blockquote>
            )}
            {f.suggested_fix && <FlagFix fix={f.suggested_fix} secret={proseSecret(f)} />}
          </div>
        ))}

        {before && after ? (
          after.source === "reference" && <SourceLine url={after.source_url} />
        ) : proposal.after ? (
          <div className="flex flex-col gap-3 rounded-[10px] border border-border px-3.5 py-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">
                {type ? TYPE_LABEL[type] : "Entry"} · {proposal.after.status}
              </div>
              <div className="font-heading text-lg font-semibold">{proposal.after.title}</div>
              {proposal.after.source === "reference" && <SourceLine url={proposal.after.source_url} />}
              {proposal.after.body && (
                <p className="m-0 mt-1 line-clamp-4 whitespace-pre-line font-heading text-[15px] text-[#e3dfd5]">
                  <SecretValue value={proposal.after.body} secret={proposal.after.status === "secret"} />
                </p>
              )}
            </div>
            <section aria-label="Drafted facts" className="flex flex-col gap-2">
              <h4 className="m-0 text-xs font-semibold uppercase tracking-[1px]">Facts to commit</h4>
              <FactList facts={proposal.after.facts} />
            </section>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded-[10px] border border-border px-3.5 py-3 text-[13px]">
            <div>This entry will be deleted from canon.</div>
            {check.dependents.length > 0 ? (
              <>
                <div className="text-muted-foreground">These entries mention it:</div>
                <div className="flex flex-wrap gap-1.5">
                  {check.dependents.map((d) => (
                    <span key={d.id} className="inline-flex items-center gap-1.5">
                      <EntityChip type={d.type} name={d.title} href={`/canon/${encodeURIComponent(d.id)}`} />
                      <span className="text-xs text-muted-foreground">{d.id}</span>
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-muted-foreground">No other entries mention it.</div>
            )}
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

function SourceLine({ url }: { url?: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <span>Source: reference (Wikipedia)</span>
      {url && /^https:\/\//.test(url) && (
        <a href={url} target="_blank" rel="noopener noreferrer" className="break-all text-accent underline underline-offset-2">
          {url}
        </a>
      )}
    </div>
  );
}

function EditForm({
  draft,
  disabled,
  onCancel,
  onSubmit,
}: {
  draft: EntryDraft;
  disabled?: boolean;
  onCancel: () => void;
  onSubmit: (edited: EntryDraft) => void;
}) {
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const [facts, setFacts] = useState<Fact[]>(draft.facts);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  const setFact = (i: number, patch: Partial<Fact>) =>
    setFacts((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      ...draft,
      title: title.trim() || draft.title,
      body,
      facts: facts.filter((f) => f.key.trim() && f.value.trim()).map((f) => ({ ...f, key: f.key.trim(), value: f.value.trim() })),
    });
  }

  return (
    <form onSubmit={submit} aria-label="Edit proposal" className="flex flex-col gap-3 rounded-[10px] border border-border-strong px-3.5 py-3">
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} className={INPUT} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Body
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={4}
          maxLength={4000}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 font-heading text-[15px] text-foreground"
        />
      </label>
      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-xs font-semibold uppercase tracking-[1px]">Facts</legend>
        {facts.map((f, i) => {
          const n = i + 1;
          const hide = f.status === "secret" && !revealed.has(i);
          return (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <input aria-label={`Fact ${n} key`} value={f.key} onChange={(e) => setFact(i, { key: e.target.value })} maxLength={40} placeholder="Key" className={`${INPUT} flex-[1_1_120px]`} />
              <input
                aria-label={`Fact ${n} value`}
                type={hide ? "password" : "text"}
                value={f.value}
                onChange={(e) => setFact(i, { value: e.target.value })}
                maxLength={200}
                placeholder="Value"
                className={`${INPUT} flex-[2_1_180px]`}
              />
              {hide && (
                <button type="button" onClick={() => setRevealed((s) => new Set(s).add(i))} aria-label={`Show secret fact ${n}`} className={BTN_SECONDARY}>
                  Show
                </button>
              )}
              <select
                aria-label={`Fact ${n} status`}
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
