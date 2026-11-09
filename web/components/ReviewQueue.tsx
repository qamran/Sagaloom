import { CHECK_FAILED_TEXT } from "@/components/ApprovalCard";
import { TYPE_DOT } from "@/lib/entity";
import { BADGE_CLASS, BADGE_LABEL, badgeOf, existingSecretOf, proposalSummary, proseSecretOf } from "@/lib/review";
import type { Decision, Entry, PendingInterrupt, Proposal } from "@/lib/types";

const ACTION_LABEL: Record<Proposal["action"], string> = { create: "New", update: "Update", delete: "Delete" };

interface Props {
  pending: PendingInterrupt;
  /** This world's entries; the summaries mask secrets exactly as the card does (fail closed until loaded). */
  canon?: Entry[];
  selectedId: string;
  chosen: Record<string, Decision>;
  onSelect: (proposalId: string) => void;
}

/** One button per pending proposal: badge, action, title and a one-line summary. */
export function ReviewQueue({ pending, canon, selectedId, chosen, onSelect }: Props) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {pending.proposals.map((p) => {
        const check = pending.checks[p.proposal_id];
        if (!check) return null;
        const draft = p.after ?? p.before;
        const badge = badgeOf(check);
        const selected = p.proposal_id === selectedId;
        const decision = chosen[p.proposal_id];
        return (
          <li key={p.proposal_id}>
            <button
              type="button"
              aria-current={selected ? "true" : undefined}
              onClick={() => onSelect(p.proposal_id)}
              className={`flex min-h-11 w-full flex-col gap-1.5 rounded-[10px] border px-3 py-2.5 text-left text-foreground ${
                selected ? "border-conflict-line bg-conflict-bg" : "border-border bg-panel-2 hover:bg-panel-3"
              }`}
            >
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_CLASS[badge]}`}>
                  {BADGE_LABEL[badge]}
                </span>
                <span>{ACTION_LABEL[p.action]}</span>
                {decision && (
                  <span className="ml-auto text-accent">
                    <span aria-hidden="true">✓</span>
                    <span className="sr-only">Decided: {decision.action.replace(/_/g, " ")}</span>
                  </span>
                )}
              </span>
              <span className="flex items-center gap-2">
                {draft && <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${TYPE_DOT[draft.type]}`} />}
                <span className="text-sm font-semibold">{draft?.title ?? "Untitled"}</span>
              </span>
              <span className="text-xs text-muted-foreground">
                {badge === "failed"
                  ? CHECK_FAILED_TEXT
                  : proposalSummary(p, check, existingSecretOf(p, canon), proseSecretOf(p, canon))}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
