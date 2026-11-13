// The Home dashboard's numbers, worked out from data the app already loads: worlds, the account's
// threads (`GET /threads`), the current world's entries and `/me`. No new API.

import { matchStatus } from "./canonFilter";
import type { Entry, Me, ThreadSummary } from "./types";

export interface WorldStats {
  chats: number;
  /** Proposals waiting for a decision, across the world's chats and imports. */
  waiting: number;
}

/** A chat the author has written in. The API titles a thread from the author's first message
 * (`thread_title` in `api/sagaloom/web/thread_list.py`), so a chat with no title has no messages
 * yet; a running chat counts while its first turn has not been summarised. */
export function hasMessages(t: ThreadSummary): boolean {
  return t.kind === "chat" && (t.title !== null || t.running);
}

/** Chats (with messages) and waiting proposals per world id, from one thread list. */
export function worldStats(threads: ThreadSummary[]): Map<string, WorldStats> {
  const out = new Map<string, WorldStats>();
  for (const t of threads) {
    const s = out.get(t.world_id) ?? { chats: 0, waiting: 0 };
    if (hasMessages(t)) s.chats += 1;
    s.waiting += t.pending;
    out.set(t.world_id, s);
  }
  return out;
}

export interface CanonHealth {
  entries: number;
  myths: number;
  rumours: number;
  secrets: number;
}

/** Entries, and for each status the entries that have it or hold a fact with it: the same entries
 * the Canon list shows when a tile opens it filtered (`matchStatus`), each counted once. */
export function canonHealth(entries: Entry[]): CanonHealth {
  return {
    entries: entries.length,
    myths: matchStatus(entries, "myth").length,
    rumours: matchStatus(entries, "rumour").length,
    secrets: matchStatus(entries, "secret").length,
  };
}

/** Newest first, by `created_at`; unreadable times sort last. */
export function newestFirst<T extends { created_at: string }>(items: T[], limit: number): T[] {
  const time = (x: T) => {
    const t = Date.parse(x.created_at);
    return Number.isNaN(t) ? -Infinity : t;
  };
  return [...items].sort((a, b) => time(b) - time(a)).slice(0, limit);
}

/** The world's chats with messages (not imports, not empty chats), newest first. */
export function recentChats(threads: ThreadSummary[], worldId: string, limit = 4): ThreadSummary[] {
  return newestFirst(
    threads.filter((t) => t.world_id === worldId && hasMessages(t)),
    limit,
  );
}

const usd = (n: number) => `$${n.toFixed(2)}`;

/** "1 Dec" from "2026-12-01", read as a UTC date like the API's budget month. */
export function resetDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export interface Credits {
  /** The big number: what is left, or "Unlimited" for the admin. */
  headline: string;
  /** The line beside it. */
  detail: string;
  /** Share of the budget used, 0-100; null when there is no limit. */
  usedPercent: number | null;
  over: boolean;
}

/** The AI credits panel: this month's budget left, the spend, and the admin's unlimited case. */
export function credits(me: Me): Credits {
  const spent = me.month_spend_usd;
  if (me.monthly_budget_usd === null) {
    return { headline: "Unlimited", detail: `${usd(spent)} used this month (admin)`, usedPercent: null, over: false };
  }
  const budget = me.monthly_budget_usd;
  const left = Math.max(0, budget - spent);
  const usedPercent = budget > 0 ? Math.min(100, (spent / budget) * 100) : 100;
  return {
    headline: usd(left),
    detail: `left of ${usd(budget)} · ${usd(spent)} used`,
    usedPercent,
    over: me.over_budget,
  };
}
