"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getReviewThreads } from "@/lib/api";
import { BADGE_CLASS, BADGE_LABEL, REVIEW_KEY } from "@/lib/review";
import { ago } from "@/lib/time";
import { useWorld } from "@/lib/world";

export const EMPTY_REVIEW =
  "Nothing to review. Every change the assistant proposes waits here until you decide.";

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
    <main className="px-4 py-6 md:px-11 md:py-[30px]">
      <div className="flex max-w-3xl flex-col gap-5">
        <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">
          Review
        </h1>
        {(error || isError) && (
          <p role="alert" className="m-0 text-conflict">
            Could not load the review queue. Is the Sagaloom API running?
          </p>
        )}
        {!isLoading && !error && !world && (
          <p className="m-0 text-muted-foreground">No world selected.</p>
        )}
        {world && isPending && !isError && (
          <p className="m-0 text-muted-foreground">Loading…</p>
        )}
        {data?.length === 0 && (
          <p className="m-0 font-heading text-[17px] text-prose-muted">
            {EMPTY_REVIEW}
          </p>
        )}
        {data && data.length > 0 && (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {data.map((t) => (
              <li key={t.thread_id}>
                <Link
                  href={`/review/${encodeURIComponent(t.thread_id)}`}
                  className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-[10px] border border-border bg-panel-2 px-3.5 py-2.5 text-foreground no-underline hover:bg-panel-3 hover:no-underline"
                >
                  {t.badge && (
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_CLASS[t.badge]}`}
                    >
                      {BADGE_LABEL[t.badge]}
                    </span>
                  )}
                  <span className="text-sm font-semibold">
                    {t.title ?? (t.kind === "import" ? "Untitled import" : "Untitled chat")}
                  </span>
                  <span className="text-xs text-muted-foreground">{t.kind === "import" ? "Import" : "Chat"}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.pending} {t.pending === 1 ? "proposal" : "proposals"}
                  </span>
                  <span className="text-xs text-muted-foreground sm:ml-auto">
                    {ago(t.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
