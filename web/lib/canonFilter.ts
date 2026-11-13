// The Canon list's status filter (`/canon?status=myth`), opened from Home's Canon health tiles.
// It matches what those tiles count (`canonHealth` in ./dashboard): whole entries with the status,
// and single facts with it inside other entries.

import type { Entry } from "./types";

export const STATUS_FILTERS = ["myth", "rumour", "secret"] as const;
export type StatusFilter = (typeof STATUS_FILTERS)[number];

/** Plural label, as on the tiles. */
export const STATUS_PLURAL: Record<StatusFilter, string> = { myth: "myths", rumour: "rumours", secret: "secrets" };

/** The `status` search param, or null when it is missing or not a filter. */
export function parseStatus(value: string | null | undefined): StatusFilter | null {
  return (STATUS_FILTERS as readonly string[]).includes(value ?? "") ? (value as StatusFilter) : null;
}

/** `/canon` or an entry's page, keeping the filter. */
export function canonHref(status: StatusFilter | null, entryId?: string): string {
  const path = entryId ? `/canon/${entryId}` : "/canon";
  return status ? `${path}?status=${status}` : path;
}

export interface StatusMatch {
  entry: Entry;
  /** The entry itself has the status. */
  whole: boolean;
  /** Keys of its facts with the status. */
  factKeys: string[];
  /** Shown only with Show secrets on: a secret entry, or any match of the secret filter. */
  secret: boolean;
}

/** Entries that have the status, or hold facts with it, in list order. */
export function matchStatus(entries: Entry[], status: StatusFilter): StatusMatch[] {
  const out: StatusMatch[] = [];
  for (const entry of entries) {
    const whole = entry.status === status;
    const factKeys = entry.facts.filter((f) => f.status === status).map((f) => f.key);
    if (!whole && factKeys.length === 0) continue;
    out.push({ entry, whole, factKeys, secret: status === "secret" || entry.status === "secret" });
  }
  return out;
}
