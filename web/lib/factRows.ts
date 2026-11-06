import { norm } from "@/lib/review";
import type { CheckResult, Entry, EntryDraft, Fact, Flag, Proposal } from "@/lib/types";

/**
 * Result column values (spec §3.7). `Changed` (no flag) marks a changed myth or rumour value:
 * beliefs never raise a retcon, but the table still shows the change. A same value whose status
 * or teller changed is `Changed` too (Ruling R8).
 */
export type FactResult =
  | "Matches"
  | "Changed (retcon)"
  | "Changed"
  | "Conflict"
  | "Possible conflict"
  | "Note"
  | "New"
  | "Removed";

export interface FactRow {
  key: string;
  /** This entry's stored facts under the key. */
  canon: Fact[];
  /** The draft's facts under the key. */
  proposed: Fact[];
  result: FactResult;
  flags: Flag[];
  /** The other entry a conflict on this key comes from (or, on a create, the flagged entry). */
  cite?: { id: string; title: string };
}

const valueSet = (facts: Fact[]) =>
  [...new Set(facts.map((f) => JSON.stringify([norm(f.value), f.status, f.told_by ?? null])))].sort().join("\n");

function resultOf(canon: Fact[], proposed: Fact[], flags: Flag[]): FactResult {
  const conflicts = flags.filter((f) => f.kind === "conflict");
  if (conflicts.some((f) => f.severity === "hard")) return "Conflict";
  if (conflicts.length) return "Possible conflict";
  if (flags.some((f) => f.kind === "retcon")) return "Changed (retcon)";
  if (flags.some((f) => f.kind === "note")) return "Note";
  if (!canon.length) return "New";
  if (!proposed.length) return "Removed";
  return valueSet(canon) === valueSet(proposed) ? "Matches" : "Changed";
}

const citeOf = (f: Flag | undefined) => (f ? { id: f.entry_id, title: f.title } : undefined);

/** The approval card's fact table: every key on either side of an update, plus keyed flags. */
export function buildFactRows(p: Proposal, c: CheckResult): FactRow[] {
  const keyed = c.flags.filter((f): f is Flag & { fact_key: string } => !!f.fact_key);
  if (p.action === "delete" || !p.after) return [];
  const after = p.after;
  const under = (facts: Fact[], key: string) => facts.filter((f) => norm(f.key) === key);

  if (p.action === "create" || !p.before) {
    return keyed.map((flag) => {
      const proposed = under(after.facts, norm(flag.fact_key));
      return {
        key: flag.fact_key,
        canon: [],
        proposed,
        result: resultOf([], proposed, [flag]),
        flags: [flag],
        cite: citeOf(flag),
      };
    });
  }

  const before = p.before;
  const keys = new Map<string, string>(); // normalised key → key as first written
  for (const f of [...before.facts, ...after.facts]) if (!keys.has(norm(f.key))) keys.set(norm(f.key), f.key);
  const rows: FactRow[] = [...keys].map(([k, key]) => {
    const canon = under(before.facts, k);
    const proposed = under(after.facts, k);
    const flags = keyed.filter((f) => norm(f.fact_key) === k);
    const otherConflict = flags.find((f) => f.kind === "conflict" && f.entry_id !== p.entry_id);
    return { key, canon, proposed, result: resultOf(canon, proposed, flags), flags, cite: citeOf(otherConflict) };
  });
  for (const flag of keyed) {
    if (keys.has(norm(flag.fact_key))) continue;
    const cite = flag.kind === "conflict" && flag.entry_id !== p.entry_id ? citeOf(flag) : undefined;
    rows.push({ key: flag.fact_key, canon: [], proposed: [], result: resultOf([], [], [flag]), flags: [flag], cite });
  }
  return rows;
}

const LINE_FIELDS = ["title", "type", "status", "aliases"] as const;
export type LineField = (typeof LINE_FIELDS)[number];

const lineOf = (e: Entry | EntryDraft, field: LineField) => (field === "aliases" ? e.aliases.join(", ") : e[field]);

/** The entry's one-line fields an update changes (aliases joined with ", "). */
export function lineDiff(before: Entry, after: EntryDraft): { field: LineField; old: string; new: string }[] {
  return LINE_FIELDS.filter((field) => lineOf(before, field) !== lineOf(after, field)).map((field) => ({
    field,
    old: lineOf(before, field),
    new: lineOf(after, field),
  }));
}
