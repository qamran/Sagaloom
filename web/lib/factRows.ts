import { norm } from "@/lib/text";
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

/** The approval card's fact table: every key on either side of an update, plus keyed flags. */
export function buildFactRows(p: Proposal, c: CheckResult): FactRow[] {
  const keyed = c.flags.filter((f): f is Flag & { fact_key: string } => !!f.fact_key);
  if (p.action === "delete" || !p.after) return [];
  const after = p.after;
  const under = (facts: Fact[], key: string) => facts.filter((f) => norm(f.key) === key);

  // Keyed flags by normalised key, in first-seen order: one row per key however many flags name it.
  const flagged = new Map<string, { key: string; flags: Flag[] }>();
  for (const flag of keyed) {
    const k = norm(flag.fact_key);
    const group = flagged.get(k);
    if (group) group.flags.push(flag);
    else flagged.set(k, { key: flag.fact_key, flags: [flag] });
  }

  if (p.action === "create" || !p.before) {
    return [...flagged].map(([k, { key, flags }]) => {
      const proposed = under(after.facts, k);
      return { key, canon: [], proposed, result: resultOf([], proposed, flags), flags };
    });
  }

  const before = p.before;
  const keys = new Map<string, string>(); // normalised key → key as first written
  for (const f of [...before.facts, ...after.facts]) if (!keys.has(norm(f.key))) keys.set(norm(f.key), f.key);
  const rows: FactRow[] = [...keys].map(([k, key]) => {
    const canon = under(before.facts, k);
    const proposed = under(after.facts, k);
    const flags = flagged.get(k)?.flags ?? [];
    return { key, canon, proposed, result: resultOf(canon, proposed, flags), flags };
  });
  for (const [k, { key, flags }] of flagged) {
    if (!keys.has(k)) rows.push({ key, canon: [], proposed: [], result: resultOf([], [], flags), flags });
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
