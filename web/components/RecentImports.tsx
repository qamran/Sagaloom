"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getImports } from "@/lib/api";
import { reviewPollMs } from "@/lib/review";
import { ago } from "@/lib/time";
import { useWorld } from "@/lib/world";

const ROW =
  "flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 rounded-[10px] border border-border bg-panel-2 px-3.5 py-2.5 text-foreground";

/** Past imports in the active world, newest first, each linking to its Review page. */
export function RecentImports() {
  const { world } = useWorld();
  const { data, isError } = useQuery({
    queryKey: ["imports", world?.id ?? ""],
    queryFn: () => getImports(world?.id as string),
    enabled: !!world,
    refetchInterval: (q) => reviewPollMs(q.state.data),
  });
  return (
    <section aria-label="Recent imports" className="flex max-w-3xl flex-col gap-2">
      <h2 className="m-0 font-heading text-xl font-medium">Recent imports</h2>
      {isError && (
        <p role="alert" className="m-0 text-conflict">
          Could not load recent imports.
        </p>
      )}
      {data?.length === 0 && <p className="m-0 text-muted-foreground">No imports yet.</p>}
      {data && data.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {data.map((t) => {
            const content = (
              <>
                <span className="text-sm font-semibold">{t.title ?? "Untitled import"}</span>
                <span className="text-xs text-muted-foreground">{ago(t.created_at)}</span>
                <span className="text-xs text-muted-foreground sm:ml-auto">
                  {t.running ? "Importing…" : `${t.pending} pending · ${t.approved} approved · ${t.rejected} rejected`}
                </span>
              </>
            );
            return (
              <li key={t.thread_id}>
                {/* Still extracting: nothing to review yet, so not a link; the import page opens it on done. */}
                {t.running ? (
                  <div className={ROW}>{content}</div>
                ) : (
                  <Link
                    href={`/review/${encodeURIComponent(t.thread_id)}`}
                    className={`${ROW} no-underline hover:bg-panel-3 hover:no-underline`}
                  >
                    {content}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
