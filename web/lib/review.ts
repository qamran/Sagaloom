import type { Badge, CheckResult, Entry, EntryDraft, Flag, PendingInterrupt, Proposal } from "@/lib/types";

/** TanStack Query key for a world's pending review threads; invalidate `["review"]` for every world. */
export const REVIEW_KEY = (worldId: string) => ["review", worldId] as const;

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
const SECRET = "a secret fact";

/**
 * A flag's fact value without the judge's key. The judge's flags (conflict, note) carry
 * `"<key>: <value>"`, where the key may be another entry's (api/sagaloom/check/contradiction.py
 * `_to_flag`); a retcon's value is the bare stored value, which may itself hold a colon.
 */
export function flagValue(f: Flag, value: string): string {
  return f.kind === "retcon" ? value : value.replace(/^[^:\n]{1,60}:\s+/, "");
}

/** True when the entry is secret, or holds facts under `key` and every one of them is secret. */
function keySecret(entry: Pick<EntryDraft, "status" | "facts"> | null | undefined, key: string) {
  if (!entry) return false;
  if (entry.status === "secret") return true;
  const under = entry.facts.filter((f) => norm(f.key) === key);
  return under.length > 0 && under.every((f) => f.status === "secret");
}

/**
 * One line about a proposal for a list: its first conflicting, else retconned, fact; else a
 * duplicate note; else what a delete touches; else the first conflict's, else note's, prose.
 * `secret` says a flag's existing side is masked.
 */
export function proposalSummary(
  p: Proposal,
  c: CheckResult,
  secret: (f: Flag) => boolean,
  /** Masks a flag's prose, like the card; defaults to `secret`. */
  proseSecret: (f: Flag) => boolean = secret,
): string {
  const first = (kind: Flag["kind"], keyed = false) => c.flags.find((f) => f.kind === kind && (!keyed || f.fact_key));
  const flag = first("conflict", true) ?? first("retcon", true);
  if (flag?.fact_key) {
    const existing =
      flag.existing_fact === null ? "not set" : secret(flag) ? SECRET : flagValue(flag, flag.existing_fact);
    // The server joins every added value under the key ("a, b"), so fail closed: any secret
    // proposed fact under the key, or a secret draft, hides the new side.
    const key = norm(flag.fact_key);
    const draftSecret =
      p.after?.status === "secret" || !!p.after?.facts.some((f) => norm(f.key) === key && f.status === "secret");
    const proposed = flag.new_fact === null ? "removed" : draftSecret ? SECRET : flagValue(flag, flag.new_fact);
    // Like FactTable: a key whose facts are all secret names the secret, so it is masked too.
    const name = keySecret(p.after, key) || keySecret(p.before, key) ? SECRET : flag.fact_key;
    return `${name}: ${existing} → ${proposed}`;
  }
  const dup = c.flags.find((f) => f.kind === "note" && !f.fact_key && f.explanation.startsWith(DUPLICATE));
  // The explanation names the other entry's title: a secret entry is cited by ID only.
  if (dup) return proseSecret(dup) ? `${DUPLICATE}${dup.entry_id}` : dup.explanation;
  if (p.action === "delete") {
    const n = c.dependents.length;
    return `Deletes this entry · ${n === 1 ? "1 entry mentions" : `${n} entries mention`} it`;
  }
  // A prose-only conflict or a keyed note: its explanation, or, when masked, the badge and the
  // cited entry's ID, as the card shows a masked flag (its Cite and a hidden explanation).
  const prose = first("conflict") ?? first("note");
  if (prose) {
    if (prose.explanation && !proseSecret(prose)) return prose.explanation;
    const label = BADGE_LABEL[prose.severity === "possible" ? "possible" : prose.kind];
    return prose.entry_id ? `${label} with ${prose.entry_id}` : label;
  }
  return "No conflicts found";
}

function secretIndex(proposal: Proposal, canon: Entry[] | undefined) {
  const byId = new Map<string, Pick<Entry, "status" | "facts">>();
  for (const e of canon ?? []) byId.set(e.id, e);
  if (proposal.before) byId.set(proposal.before.id, proposal.before);
  const unknown = (id: string) => !!id && id !== proposal.entry_id && canon === undefined;
  return { byId, unknown };
}

/**
 * Whether a flag's existing side is secret, as the card masks it: the server's mark, a secret fact
 * or entry among `canon` (plus the proposal's own `before`), and fail closed: until `canon` has
 * loaded, any flag citing another entry counts as secret (R12.12).
 */
export function existingSecretOf(proposal: Proposal, canon: Entry[] | undefined): (f: Flag) => boolean {
  const { byId, unknown } = secretIndex(proposal, canon);
  return (f) => f.existing_secret || unknown(f.entry_id) || isSecretFact(byId.get(f.entry_id), f.fact_key, f.existing_fact);
}

/**
 * Whether a flag's text about the existing side (a quote, or the prose of a keyless flag) is
 * secret. A quote can come from a secret fact's text, so a keyless flag is masked when its entry
 * holds any secret.
 */
export function textSecretOf(proposal: Proposal, canon: Entry[] | undefined): (f: Flag) => boolean {
  const { byId, unknown } = secretIndex(proposal, canon);
  const existing = existingSecretOf(proposal, canon);
  return (f) => {
    if (f.fact_key) return existing(f);
    if (f.existing_secret || unknown(f.entry_id)) return true;
    const e = byId.get(f.entry_id);
    return !!e && (e.status === "secret" || e.facts.some((x) => x.status === "secret"));
  };
}

/** True when the draft side is a secret entry or holds any secret fact. */
export const draftHoldsSecret = (p: Proposal) =>
  !!p.after && (p.after.status === "secret" || p.after.facts.some((x) => x.status === "secret"));

/** Prose about a flag (explanation, suggested fix) can quote either side. */
export function proseSecretOf(proposal: Proposal, canon: Entry[] | undefined): (f: Flag) => boolean {
  const text = textSecretOf(proposal, canon);
  const draft = draftHoldsSecret(proposal);
  return (f) => text(f) || draft;
}
