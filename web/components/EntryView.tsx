"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { FactList } from "@/components/FactList";
import { ApiError, getEntry } from "@/lib/api";
import { TYPE_LABEL, TYPE_PLURAL, TYPE_TEXT } from "@/lib/entity";
import { importedSections } from "@/lib/imported";
import { markTour } from "@/lib/tour";
import { useWorld } from "@/lib/world";

const CARD = "rounded-xl border border-border bg-panel-2 px-5 py-[18px]";

/** Basic read-only entry page (R12.11): meta line, body, Facts panel. Entry links are not shown in M1. */
export function EntryView({ entryId }: { entryId: string }) {
  const { world } = useWorld();
  const [revealed, setRevealed] = useState(false);

  const { data: entry, isLoading, error } = useQuery({
    queryKey: ["entry", world?.id, entryId],
    queryFn: () => getEntry(world!.id, entryId),
    enabled: !!world,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });

  useEffect(() => {
    if (entry) markTour("visited");
  }, [entry]);

  if (isLoading || !world) return <p className="text-muted-foreground">Loading entry…</p>;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="m-0 font-heading text-3xl font-medium">Entry not found</h1>
        <p className="m-0 text-muted-foreground">
          There is no entry {entryId} in {world.name}.
        </p>
        <Link href="/canon">← Back to Canon</Link>
      </div>
    );
  }
  if (error || !entry) {
    return (
      <p role="alert" className="text-conflict">
        Could not load this entry.
      </p>
    );
  }

  const hidden = entry.status === "secret" && !revealed;
  const typeText = TYPE_TEXT[entry.type];
  const status = entry.status.charAt(0).toUpperCase() + entry.status.slice(1);
  const imported = entry.trusted ? [] : importedSections(entry.body);

  return (
    <div className="flex flex-wrap items-start gap-7">
      <article className="flex max-w-[720px] min-w-0 flex-[999_1_460px] flex-col gap-[18px]">
        <Link href="/canon" className="text-[13px] text-muted-foreground no-underline hover:text-foreground">
          ← All {TYPE_PLURAL[entry.type].toLowerCase()}
        </Link>

        {hidden ? (
          <section className={`${CARD} flex flex-col items-start gap-3`}>
            <h1 className="m-0 font-heading text-2xl font-medium">Secret entry</h1>
            <p className="m-0 text-muted-foreground">
              This entry is hidden so the screen is safe to share.
            </p>
            <button
              type="button"
              onClick={() => setRevealed(true)}
              className="min-h-11 rounded-lg border border-border-strong px-4 text-[13px] hover:bg-panel-3"
            >
              Show
            </button>
          </section>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <div className={`text-xs uppercase tracking-[1px] ${typeText}`}>
                {TYPE_LABEL[entry.type]} · {status} · {entry.id}
              </div>
              <h1 className="m-0 font-heading text-[clamp(30px,5vw,42px)] font-medium leading-[1.1]">
                {entry.title}
              </h1>
              <div className="flex flex-wrap gap-1.5 text-xs">
                {entry.aliases.map((a) => (
                  <span
                    key={a}
                    className="rounded-full border border-border-strong px-2.5 py-0.5 text-[#c9c6bd]"
                  >
                    {a}
                  </span>
                ))}
                <span className="rounded-full border border-border-strong px-2.5 py-0.5 text-muted-foreground">
                  v{entry.version} · edited {new Date(entry.updated_at).toLocaleDateString("en-GB")}
                </span>
              </div>
              {imported.length > 0 && (
                <div className="flex flex-col gap-0.5 text-xs">
                  <span className={`uppercase tracking-[1px] ${typeText}`}>Contains imported text</span>
                  <ul className="m-0 flex list-none flex-wrap gap-x-3 p-0 text-muted-foreground">
                    {imported.map((label, i) => (
                      <li key={i}>{label}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <section className={CARD}>
              <h2 className={`m-0 mb-2 text-xs font-semibold uppercase tracking-[1px] ${typeText}`}>
                Description
              </h2>
              <p className="m-0 whitespace-pre-line font-heading text-[17px] leading-[1.65] text-[#e3dfd5]">
                {entry.body || "No description yet."}
              </p>
            </section>
          </>
        )}
      </article>

      <aside
        aria-label="Facts"
        className="flex max-w-xs min-w-0 flex-[1_1_260px] flex-col gap-3.5 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
      >
        <div>
          <h2 className="m-0 text-xs font-semibold uppercase tracking-[1px]">Facts</h2>
          <div className="mt-1 text-xs text-muted-foreground">
            Short claims the contradiction check compares across the world.
          </div>
        </div>
        {hidden ? (
          <p className="m-0 text-sm text-muted-foreground">Hidden with the entry.</p>
        ) : (
          <FactList facts={entry.facts} />
        )}
      </aside>
    </div>
  );
}
