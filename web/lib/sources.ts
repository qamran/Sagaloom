import type { EntrySource } from "@/lib/types";

export const LICENCE_NOT_REPORTED = "licence not reported";

type WithSources = { sources?: Pick<EntrySource, "nc">[] | { nc?: boolean }[] };

/** True when any page the entry came from is licensed for non-commercial use only (R11.6.13). */
export function entryIsNc(e: WithSources | null | undefined): boolean {
  return !!e?.sources?.some((s) => s.nc === true);
}

/** The licence as reported: its text, else its URL (R-W3-2), else `licence not reported`.
 *  A missing licence is never filled in. */
export function licenceText(s: { licence?: string | null; licence_url?: string | null }): string {
  if (s.licence?.trim()) return s.licence;
  if (s.licence_url?.trim()) return s.licence_url;
  return LICENCE_NOT_REPORTED;
}

/** The one rule for linking a source URL: https only (the server stores nothing else). */
export function isHttpsUrl(url: string | null | undefined): url is string {
  return !!url && /^https:\/\//i.test(url);
}
