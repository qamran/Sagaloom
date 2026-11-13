"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { getEntries } from "@/lib/api";
import {
  canonHref,
  matchStatus,
  parseStatus,
  STATUS_PLURAL,
  type StatusFilter,
} from "@/lib/canonFilter";
import { TYPE_DOT, TYPE_ORDER, TYPE_PLURAL } from "@/lib/entity";
import { useShowSecrets } from "@/lib/secrets";
import { entryIsNc } from "@/lib/sources";
import type { Entry, EntryType } from "@/lib/types";
import { useWorld } from "@/lib/world";

const NAV =
  "flex max-h-72 w-full flex-col gap-3.5 overflow-y-auto border-b border-border bg-panel px-3 py-[18px] text-[13px] md:max-h-none md:w-60 md:shrink-0 md:overflow-visible md:border-b-0 md:border-r";

/** Left column of the Canon tab: entries grouped by type, with search (R12.2) and the status
 * filter `?status=myth|rumour|secret` that Home's Canon health tiles open. */
export function CanonList() {
  // useSearchParams needs a Suspense boundary (as on the Studio page).
  return (
    <Suspense fallback={<nav aria-label="Entries" className={NAV} />}>
      <List />
    </Suspense>
  );
}

function List() {
  const { world } = useWorld();
  const pathname = usePathname();
  const status = parseStatus(useSearchParams().get("status"));
  const [search, setSearch] = useState("");
  const [showSecrets, setShowSecrets] = useShowSecrets(world?.id);
  // Folded type groups, per world. The list lives in the Canon layout, so this lasts while the
  // author moves between entries. A search opens every group, so no match is ever hidden.
  const [folded, setFolded] = useState<Record<string, EntryType[]>>({});
  const worldFolded = folded[world?.id ?? ""] ?? [];
  const toggleGroup = (type: EntryType) => {
    if (!world) return;
    const next = worldFolded.includes(type)
      ? worldFolded.filter((t) => t !== type)
      : [...worldFolded, type];
    setFolded({ ...folded, [world.id]: next });
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["entries", world?.id],
    queryFn: () => getEntries(world!.id),
    enabled: !!world,
  });

  const needle = search.trim().toLowerCase();
  // With a status filter: only entries that have the status or hold facts with it, with those facts' keys.
  const matches = status ? matchStatus(data ?? [], status) : null;
  const factKeys = new Map(matches?.map((m) => [m.entry.id, m.factKeys]) ?? []);
  const secretIds = new Set(
    matches ? matches.filter((m) => m.secret).map((m) => m.entry.id) : [],
  );
  const isSecret = (e: Entry) =>
    matches ? secretIds.has(e.id) : e.status === "secret";
  const all = matches ? matches.map((m) => m.entry) : (data ?? []);
  // Secret entries (and every match of the secret filter) stay out of the visible list and its search
  // until revealed; the footer button shows their count.
  const hiddenCount = all.filter(isSecret).length;
  const visible = all.filter(
    (e) =>
      (showSecrets || !isSecret(e)) &&
      (!needle ||
        e.title.toLowerCase().includes(needle) ||
        e.aliases.some((a) => a.toLowerCase().includes(needle))),
  );

  return (
    <nav aria-label="Entries" className={NAV}>
      {status && <FilterChip status={status} />}
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
      {data &&
        visible.length === 0 &&
        (needle || all.length === 0 || status) && (
          <p className="m-0 text-muted-foreground">
            {needle
              ? "No entries match."
              : status && all.length === 0
                ? `No ${STATUS_PLURAL[status]} in this world.`
                : status
                  ? status === "secret"
                    ? "Secrets are hidden until you show them."
                    : `These ${STATUS_PLURAL[status]} are in secret entries, hidden until you show them.`
                  : "No entries yet. Ask the assistant in Chat to add one."}
          </p>
        )}

      {TYPE_ORDER.map((type) => {
        const group = visible.filter((e) => e.type === type);
        if (group.length === 0) return null;
        const open = !!needle || !worldFolded.includes(type);
        return (
          <div key={type} className="flex flex-col gap-0.5">
            <button
              type="button"
              aria-expanded={open}
              aria-controls={`canon-group-${type}`}
              onClick={() => toggleGroup(type)}
              className="flex min-h-8 w-full items-center gap-2 rounded-md px-1.5 py-0.5 text-left text-xs font-semibold text-muted-foreground hover:bg-panel-3 hover:text-foreground"
            >
              <span
                aria-hidden="true"
                className={`size-2 shrink-0 rounded-full ${TYPE_DOT[type]}`}
              />
              {TYPE_PLURAL[type]}{" "}
              <span className="font-normal">{group.length}</span>
              <span
                aria-hidden="true"
                className={`ml-auto text-[10px] transition-transform ${open ? "rotate-90" : ""}`}
              >
                ▶
              </span>
            </button>
            <div id={`canon-group-${type}`} className="flex flex-col gap-0.5">
              {open &&
                group.map((e) => {
                  const active = pathname === `/canon/${e.id}`;
                  const keys = factKeys.get(e.id) ?? [];
                  return (
                    <Link
                      key={e.id}
                      href={canonHref(status, e.id)}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-11 items-center rounded-md py-1 pl-[14px] pr-1.5 text-foreground no-underline hover:text-foreground hover:no-underline hover:bg-panel-3 md:min-h-8 ${
                        active ? "bg-row-active font-semibold" : ""
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        data-type-dot
                        className={`mr-2 size-2 shrink-0 rounded-full ${TYPE_DOT[e.type]}`}
                      />
                      <span>
                        {e.title}
                        {(e.status === "myth" ||
                          e.status === "rumour" ||
                          e.status === "secret") && (
                          <span className="ml-1 text-[11px] font-normal text-myth">
                            · {e.status}
                          </span>
                        )}
                        {entryIsNc(e) && (
                          <span
                            title="Non-commercial licence"
                            className="ml-1.5 rounded-full border border-conflict-line px-1.5 text-[10px] font-normal text-conflict-text"
                          >
                            NC
                          </span>
                        )}
                        {status && keys.length > 0 && (
                          <span className="block text-[11px] font-normal text-muted-foreground">
                            {keys.join(", ")}{" "}
                            <span className="text-myth">· {status}</span>
                          </span>
                        )}
                      </span>
                    </Link>
                  );
                })}
            </div>
          </div>
        );
      })}

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setShowSecrets(!showSecrets)}
          className="min-h-11 rounded-lg border border-border-strong px-3 text-left text-xs text-muted-foreground hover:bg-panel-3 sm:min-h-9"
        >
          {secretsLabel(showSecrets, hiddenCount, status)}
        </button>
      )}
    </nav>
  );
}

function secretsLabel(
  shown: boolean,
  n: number,
  status: StatusFilter | null,
): string {
  if (status === "secret")
    return shown
      ? "Hide secrets"
      : `Show ${n} ${n === 1 ? "secret" : "secrets"}`;
  return shown
    ? "Hide secret entries"
    : `Show ${n} secret ${n === 1 ? "entry" : "entries"}`;
}

/** "Showing myths ✕": the active status filter, and the way back to the whole list. */
function FilterChip({ status }: { status: StatusFilter }) {
  const pathname = usePathname();
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-myth bg-panel-3 py-1 pl-3 pr-1 text-xs text-myth">
      <span>Showing {STATUS_PLURAL[status]}</span>
      <Link
        href={pathname}
        aria-label="Clear filter"
        className="flex min-h-8 min-w-8 items-center justify-center rounded-md text-sm text-myth no-underline hover:bg-panel-2 hover:text-myth hover:no-underline"
      >
        ✕
      </Link>
    </div>
  );
}
