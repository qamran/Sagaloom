"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getReviewThreads } from "@/lib/api";
import { BADGE_CLASS, BADGE_LABEL, REVIEW_KEY } from "@/lib/review";
import { useWorld } from "@/lib/world";

export const EMPTY_REVIEW = "Nothing to review. Every change the assistant proposes waits here until you decide.";

/** "5 min ago", "2 h ago", "3 d ago"; empty for a missing or unreadable time. */
function ago(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const min = Math.max(0, Math.floor((Date.now() - then) / 60_000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  if (min < 1440) return `${Math.floor(min / 60)} h ago`;
  return `${Math.floor(min / 1440)} d ago`;
}

/** The Review tab: conversations with proposals waiting for a decision, newest first. */
export function ReviewList() {
  const { world, isLoading, error } = useWorld();
  const { data, isError, isPending } = useQuery({
    queryKey: REVIEW_KEY(world?.id ?? ""),
    queryFn: () => getReviewThreads(world?.id as string),
    enabled: !!world,
    refetchInterval: 15000,
  });

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">Review</h1>
      {(error || (!isLoading && !world) || isError) && (
        <p role="alert" className="m-0 text-conflict">
          Could not load the review queue. Is the Sagaloom API running?
        </p>
      )}
      {world && isPending && !isError && <p className="m-0 text-muted-foreground">Loading…</p>}
      {data?.length === 0 && <p className="m-0 font-heading text-[17px] text-[#c9c6bd]">{EMPTY_REVIEW}</p>}
      {data && data.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {data.map((t) => (
            <li key={t.thread_id}>
              <Link
                href={`/review/${encodeURIComponent(t.thread_id)}`}
                className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-[10px] border border-border bg-panel-2 px-3.5 py-2.5 text-foreground no-underline hover:bg-panel-3 hover:no-underline"
              >
                {t.badge && (
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_CLASS[t.badge]}`}>
                    {BADGE_LABEL[t.badge]}
                  </span>
                )}
                <span className="text-sm font-semibold">{t.title ?? "Untitled chat"}</span>
                <span className="text-xs text-muted-foreground">Chat</span>
                <span className="text-xs text-muted-foreground">
                  {t.pending} {t.pending === 1 ? "proposal" : "proposals"}
                </span>
                <span className="text-xs text-muted-foreground sm:ml-auto">{ago(t.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
