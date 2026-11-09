"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { getEntries } from "@/lib/api";
import { TYPE_DOT, TYPE_ORDER, TYPE_PLURAL } from "@/lib/entity";
import { useShowSecrets } from "@/lib/secrets";
import { useWorld } from "@/lib/world";

/** Left column of the Canon tab: entries grouped by type, with search (R12.2). */
export function CanonList() {
  const { world } = useWorld();
  const pathname = usePathname();
  const [search, setSearch] = useState("");
  const [showSecrets, setShowSecrets] = useShowSecrets(world?.id);

  const { data, isLoading, error } = useQuery({
    queryKey: ["entries", world?.id],
    queryFn: () => getEntries(world!.id),
    enabled: !!world,
  });

  const needle = search.trim().toLowerCase();
  const all = data ?? [];
  // Secret entries are left out of the visible list and its search until revealed; the footer button shows their count.
  const hiddenCount = all.filter((e) => e.status === "secret").length;
  const entries = all.filter(
    (e) =>
      (showSecrets || e.status !== "secret") &&
      (!needle ||
        e.title.toLowerCase().includes(needle) ||
        e.aliases.some((a) => a.toLowerCase().includes(needle))),
  );
  const visible = entries;

  return (
    <nav
      aria-label="Entries"
      className="flex max-h-72 w-full flex-col gap-3.5 overflow-y-auto border-b border-border bg-panel px-3 py-[18px] text-[13px] md:max-h-none md:w-60 md:shrink-0 md:overflow-visible md:border-b-0 md:border-r"
    >
      <div>
        <label htmlFor="canon-search" className="sr-only">
          Search entries
        </label>
        <input
          id="canon-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search canon"
          className="min-h-11 w-full rounded-lg border border-border bg-background px-3 text-[13px] text-foreground placeholder:text-muted-foreground sm:min-h-9"
        />
      </div>

      {isLoading && <p className="m-0 text-muted-foreground">Loading entries…</p>}
      {error && (
        <p role="alert" className="m-0 text-conflict">
          Could not load entries.
        </p>
      )}
      {data && visible.length === 0 && (needle || all.length === 0) && (
        <p className="m-0 text-muted-foreground">
          {needle ? "No entries match." : "No entries yet. Ask the assistant in Chat to add one."}
        </p>
      )}

      {TYPE_ORDER.map((type) => {
        const group = visible.filter((e) => e.type === type);
        if (group.length === 0) return null;
        return (
          <div key={type} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2 px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
              <span aria-hidden="true" className={`size-2 rounded-full ${TYPE_DOT[type]}`} />
              {TYPE_PLURAL[type]}
            </div>
            {group.map((e) => {
              const href = `/canon/${e.id}`;
              const active = pathname === href;
              return (
                <Link
                  key={e.id}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-11 items-center rounded-md py-1 pl-[14px] pr-1.5 text-foreground no-underline hover:text-foreground hover:no-underline hover:bg-panel-3 md:min-h-8 ${
                    active ? "bg-[#1f2725] font-semibold" : ""
                  }`}
                >
                  <span aria-hidden="true" data-type-dot className={`mr-2 size-2 shrink-0 rounded-full ${TYPE_DOT[e.type]}`} />
                  <span>
                    {e.title}
                    {(e.status === "myth" || e.status === "rumour" || e.status === "secret") && (
                      <span className="ml-1 text-[11px] font-normal text-myth">· {e.status}</span>
                    )}
                  </span>
                </Link>
              );
            })}
          </div>
        );
      })}

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setShowSecrets(!showSecrets)}
          className="min-h-11 rounded-lg border border-border-strong px-3 text-left text-xs text-muted-foreground hover:bg-panel-3 sm:min-h-9"
        >
          {showSecrets
            ? "Hide secret entries"
            : `Show ${hiddenCount} secret ${hiddenCount === 1 ? "entry" : "entries"}`}
        </button>
      )}
    </nav>
  );
}
