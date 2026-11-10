import type { EntrySource } from "@/lib/types";

export const LICENCE_NOT_REPORTED = "licence not reported";

type WithSources = { sources?: Pick<EntrySource, "nc">[] | { nc?: boolean }[] };

/** True when any page the entry came from is licensed for non-commercial use only (R11.6.13). */
export function entryIsNc(e: WithSources | null | undefined): boolean {
  return !!e?.sources?.some((s) => s.nc === true);
}

/** The licence as reported, or `licence not reported`: a missing licence is never filled in. */
export function licenceText(s: { licence?: string | null }): string {
  return s.licence?.trim() ? s.licence : LICENCE_NOT_REPORTED;
}
