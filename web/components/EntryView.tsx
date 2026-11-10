"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EntityChip } from "@/components/EntityChip";
import { FactList } from "@/components/FactList";
import { ApiError, getEntries, getEntry, getMentions } from "@/lib/api";
import { TYPE_LABEL, TYPE_PLURAL, TYPE_TEXT } from "@/lib/entity";
import { importedSections } from "@/lib/imported";
import { sectionsOf } from "@/lib/sections";
import { entryIsNc, isHttpsUrl, licenceText } from "@/lib/sources";
import { useShowSecrets } from "@/lib/secrets";
import { markTour } from "@/lib/tour";
import { useWorld } from "@/lib/world";

const CARD = "rounded-xl border border-border bg-panel-2 px-5 py-[18px]";

/** Entry page: meta line, one card per body section, provenance, Facts panel and who mentions it. Entry links are not shown. */
export function EntryView({ entryId }: { entryId: string }) {
  const { world } = useWorld();
  const [revealed, setRevealed] = useState(false);
  const [worldShown] = useShowSecrets(world?.id);

  const { data: entry, isLoading, error } = useQuery({
    queryKey: ["entry", world?.id, entryId],
    queryFn: () => getEntry(world!.id, entryId),
    enabled: !!world,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });

  // Same key as the Canon list, so this is usually cached; refs and tellers chip from it.
  const { data: worldEntries } = useQuery({
    queryKey: ["entries", world?.id],
    queryFn: () => getEntries(world!.id),
    enabled: !!world,
  });

  const hiddenSecret = entry?.status === "secret" && !worldShown && !revealed;
  const { data: mentions, isError: mentionsError } = useQuery({
    queryKey: ["mentions", world?.id, entryId],
    queryFn: () => getMentions(world!.id, entryId),
    enabled: !!world && !!entry && !hiddenSecret,
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

  const hidden = entry.status === "secret" && !worldShown && !revealed;
  const typeText = TYPE_TEXT[entry.type];
  const status = entry.status.charAt(0).toUpperCase() + entry.status.slice(1);
  const imported = entry.trusted ? [] : importedSections(entry.body);
  const importedItems = !entry.trusted && entry.source === "user" && imported.length === 0 ? ["the whole entry"] : imported;
  const sections = sectionsOf(entry.body);
  const provenance =
    entry.source === "user"
      ? "Source: your notes"
      : entry.source === "reference"
        ? "Source: Wikipedia reference"
        : "Source: official canon";

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
                    className="rounded-full border border-border-strong px-2.5 py-0.5 text-prose-muted"
                  >
                    {a}
                  </span>
                ))}
                <span className="rounded-full border border-border-strong px-2.5 py-0.5 text-muted-foreground">
                  v{entry.version} · edited {new Date(entry.updated_at).toLocaleDateString("en-GB")}
                </span>
              </div>
              {importedItems.length > 0 && (
                <div className="flex flex-col gap-0.5 text-xs">
                  <span className={`uppercase tracking-[1px] ${typeText}`}>Contains imported text</span>
                  <ul className="m-0 flex list-none flex-wrap gap-x-3 p-0 text-muted-foreground">
                    {importedItems.map((label, i) => (
                      <li key={i}>{label}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1 text-xs text-muted-foreground">
              <div>
                {provenance}
                {entry.source_url && (
                  <>
                    {" · "}
                    {isHttpsUrl(entry.source_url) ? (
                      <a href={entry.source_url} target="_blank" rel="noopener noreferrer">
                        {entry.source_url}
                      </a>
                    ) : (
                      <span>{entry.source_url}</span>
                    )}
                  </>
                )}
              </div>
              {!entry.trusted && <div className={`uppercase tracking-[1px] ${typeText}`}>Untrusted source</div>}
            </div>

            {entry.sources.length > 0 && (
              <section aria-label="Sources" className="flex flex-col gap-1 text-xs text-muted-foreground">
                <h2 className={`m-0 text-xs font-semibold uppercase tracking-[1px] ${typeText}`}>
                  Sources
                  {entryIsNc(entry) && (
                    <span className="ml-2 rounded-full border border-conflict-line px-2 py-px font-normal normal-case tracking-normal text-conflict-text">
                      NC
                    </span>
                  )}
                </h2>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
                  {entry.sources.map((s, i) => (
                    <li key={i}>
                      {isHttpsUrl(s.url) ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer">
                          {s.url}
                        </a>
                      ) : (
                        <span>{s.url}</span>
                      )}
                      {" · "}
                      {licenceText(s)}
                      {s.nc && " · NC"}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {sections.map((sec, i) => (
              <section key={i} className={CARD}>
                <h2
                  className={`m-0 mb-2 text-xs font-semibold uppercase tracking-[1px] ${
                    sec.imported ? typeText : "text-muted-foreground"
                  }`}
                >
                  {sec.heading}
                </h2>
                <p className="m-0 whitespace-pre-line font-heading text-[17px] leading-[1.65] text-prose">
                  {sec.text || (i === 0 ? "No description yet." : "")}
                </p>
              </section>
            ))}
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
          <FactList facts={entry.facts} entries={worldEntries} />
        )}
        {!hidden && (
          <div className="flex flex-col gap-2 border-t border-border pt-3.5">
            <h3 className="m-0 text-xs font-semibold uppercase tracking-[1px]">Mentioned in</h3>
            {mentionsError ? (
              <p className="m-0 text-sm text-muted-foreground">Could not load mentions.</p>
            ) : mentions && mentions.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {mentions.map((m) =>
                  m.status === "secret" && !worldShown ? (
                    <EntityChip key={m.id} type={m.type} name="Secret entry" />
                  ) : (
                    <EntityChip key={m.id} type={m.type} name={m.title} href={`/canon/${m.id}`} />
                  ),
                )}
              </div>
            ) : (
              mentions && <p className="m-0 text-sm text-muted-foreground">No other entries mention it.</p>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
