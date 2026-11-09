import type { Entry } from "./types";

export type Named = Pick<Entry, "id" | "title" | "type" | "aliases" | "status">;
export type Piece = string | { entry: Named; text: string };

const MIN_NAME = 3;
// Same length as the straight quote, so match offsets still index the original text.
const QUOTES: Record<string, string> = { "‘": "'", "’": "'", "“": '"', "”": '"' };
const straight = (s: string) => s.replace(/[‘’“”]/g, (c) => QUOTES[c]);
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const visible = (entries: Named[], showSecrets: boolean) =>
  entries.filter((e) => showSecrets || e.status !== "secret");

/**
 * Split text into plain strings and entries it names (id, title or alias). Case-insensitive, on
 * word boundaries, longest name first. A secret entry never matches while hidden.
 */
export function linkEntities(text: string, entries: Named[], showSecrets: boolean): Piece[] {
  const byName = new Map<string, Named>();
  for (const e of visible(entries, showSecrets)) {
    byName.set(e.id.toLowerCase(), e);
    for (const n of [e.title, ...e.aliases]) {
      const key = straight(n).trim().replace(/\s+/g, " ").toLowerCase();
      if (key.length >= MIN_NAME && !byName.has(key)) byName.set(key, e);
    }
  }
  if (byName.size === 0 || !text) return [text];
  const names = [...byName.keys()].sort((a, b) => b.length - a.length);
  const re = new RegExp(
    `(?<![\\p{L}\\p{N}_])(?:${names.map((n) => escape(n).replace(/ /g, "\\s+")).join("|")})(?![\\p{L}\\p{N}_])`,
    "giu",
  );
  const hay = straight(text);
  const out: Piece[] = [];
  let last = 0;
  for (const m of hay.matchAll(re)) {
    const entry = byName.get(m[0].replace(/\s+/g, " ").toLowerCase());
    if (!entry) continue;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push({ entry, text: text.slice(m.index, m.index + m[0].length) });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out.length ? out : [text];
}

/** Entries whose title or alias starts with, or else contains, the query. Secrets only when shown. */
export function suggestEntries(query: string, entries: Named[], showSecrets: boolean, limit = 8): Named[] {
  const q = straight(query).trim().toLowerCase();
  const rank = (e: Named): number => {
    let best = 3;
    for (const n of [e.title, ...e.aliases]) {
      const s = straight(n).toLowerCase();
      if (s.startsWith(q)) return 0;
      if (s.includes(q)) best = 1;
    }
    return best;
  };
  return visible(entries, showSecrets)
    .map((e) => ({ e, r: rank(e) }))
    .filter((x) => x.r < 3)
    .sort((a, b) => a.r - b.r)
    .slice(0, limit)
    .map((x) => x.e);
}
