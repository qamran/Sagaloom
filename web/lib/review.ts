import type { Badge, CheckResult, EntryDraft, Flag, PendingInterrupt, Proposal } from "@/lib/types";

/** Badge labels, worst first (spec §3.8). The card says "No conflicts found" in place of "Clear". */
export const BADGE_LABEL: Record<Badge, string> = {
  conflict: "Conflict",
  failed: "Check failed",
  possible: "Possible conflict",
  retcon: "Retcon",
  note: "Note",
  clear: "Clear",
};

/** Colours from the Global Constraints badge table, with the text colour each one needs. */
export const BADGE_CLASS: Record<Badge, string> = {
  conflict: "bg-conflict text-background",
  failed: "bg-destructive text-background",
  possible: "border border-conflict text-conflict",
  retcon: "bg-event text-background",
  note: "bg-myth text-background",
  clear: "bg-accent text-background",
};

/** The server's badge; for a result without one, the same precedence as api/sagaloom/check/badge.py. */
export function badgeOf(check: CheckResult): Badge {
  if (check.badge) return check.badge;
  if (check.verdict === "failed") return "failed";
  const conflicts = check.flags.filter((f) => f.kind === "conflict");
  if (conflicts.some((f) => f.severity === "hard")) return "conflict";
  if (conflicts.length) return "possible";
  if (check.flags.some((f) => f.kind === "retcon")) return "retcon";
  return check.flags.length ? "note" : "clear";
}

/** "Checked facts · 1 conflict, 1 retcon" for the pending interrupt. */
export function checkSummary(p: PendingInterrupt): { text: string; warn: boolean } {
  const checks = Object.values(p.checks);
  if (checks.some((c) => c.verdict === "failed")) return { text: "Check failed", warn: true };
  const count = (kind: string) => checks.reduce((n, c) => n + c.flags.filter((f) => f.kind === kind).length, 0);
  const parts = (
    [
      ["conflict", "conflict", "conflicts"],
      ["retcon", "retcon", "retcons"],
      ["note", "note", "notes"],
    ] as const
  )
    .map(([kind, one, many]) => [count(kind), one, many] as const)
    .filter(([n]) => n > 0)
    .map(([n, one, many]) => `${n} ${n === 1 ? one : many}`);
  const warn = checks.some((c) => c.verdict === "conflict" || c.verdict === "possible") || parts.length > 0;
  return { text: parts.length ? parts.join(", ") : "no conflicts found", warn };
}

/** Keys and values compare like api/sagaloom/store/canon.py `norm`. */
export const norm = (s: string) =>
  s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').toLowerCase().split(/\s+/).filter(Boolean).join(" ");

/** True when `value` under `key` is (or most likely is) a secret fact of `entry`. */
export function isSecretFact(
  entry: Pick<EntryDraft, "status" | "facts"> | null | undefined,
  key: string | null,
  value: string | null,
) {
  if (!entry) return false;
  if (entry.status === "secret") return true;
  if (key === null || value === null) return false;
  const withKey = entry.facts.filter((f) => norm(f.key) === norm(key));
  const exact = withKey.find((f) => f.value === value);
  if (exact) return exact.status === "secret";
  return withKey.length > 0 && withKey.every((f) => f.status === "secret");
}

const DUPLICATE = "Possible duplicate of ";

/**
 * One line about a proposal for a list: its first conflicting, else retconned, fact; else a
 * duplicate note; else what a delete touches. `secret` says a flag's existing side is masked.
 */
export function proposalSummary(p: Proposal, c: CheckResult, secret: (f: Flag) => boolean): string {
  const keyed = (kind: Flag["kind"]) => c.flags.find((f) => f.kind === kind && f.fact_key);
  const flag = keyed("conflict") ?? keyed("retcon");
  if (flag?.fact_key) {
    const existing = flag.existing_fact === null ? "not set" : secret(flag) ? "a secret fact" : flag.existing_fact;
    const proposed =
      flag.new_fact === null
        ? "removed"
        : isSecretFact(p.after, flag.fact_key, flag.new_fact)
          ? "a secret fact"
          : flag.new_fact;
    return `${flag.fact_key}: ${existing} → ${proposed}`;
  }
  const dup = c.flags.find((f) => f.kind === "note" && !f.fact_key && f.explanation.startsWith(DUPLICATE));
  // The explanation names the other entry's title: a secret entry is cited by ID only.
  if (dup) return secret(dup) ? `${DUPLICATE}${dup.entry_id}` : dup.explanation;
  if (p.action === "delete") {
    const n = c.dependents.length;
    return `Deletes this entry · ${n === 1 ? "1 entry mentions" : `${n} entries mention`} it`;
  }
  return "No conflicts found";
}
