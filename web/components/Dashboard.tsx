"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { getEntries, getReviewThreads, getThreads } from "@/lib/api";
import { canonHref } from "@/lib/canonFilter";
import { canonHealth, credits, newestFirst, recentChats, resetDay, worldStats } from "@/lib/dashboard";
import { useMe } from "@/lib/me";
import { BADGE_CLASS, BADGE_LABEL, REVIEW_KEY, reviewPollMs } from "@/lib/review";
import { useShowSecrets } from "@/lib/secrets";
import { ago } from "@/lib/time";
import { markTour, TOUR_STEPS, useTour, type TourStep } from "@/lib/tour";
import type { Entry, Me, World } from "@/lib/types";
import { useWorld } from "@/lib/world";

const PANEL = "flex min-h-0 flex-col gap-2.5 rounded-[14px] border border-border bg-panel p-4";
const H2 = "m-0 text-[17px] font-semibold text-foreground";
const ROW =
  "flex flex-col gap-1 rounded-[10px] border border-border bg-panel-2 px-3.5 py-3 text-foreground no-underline hover:bg-panel-3 hover:no-underline hover:text-foreground";
const MUTED = "m-0 text-[13px] text-muted-foreground";

const TYPE_CLASS: Record<Entry["type"], string> = {
  character: "text-character",
  place: "text-place",
  faction: "text-faction",
  item: "text-item",
  rule: "text-rule",
  event: "text-event",
};

const TOUR_CARDS: Record<TourStep, { title: string; hint: string; href: string }> = {
  visited: { title: "Browse an entry", hint: "Open Sky of Velmar", href: "/canon/ent_0007" },
  chatted: {
    title: "Ask your canon",
    hint: "Answers cite entry IDs",
    href: `/chat?prompt=${encodeURIComponent("How many moons does Velmar have?")}`,
  },
  conflict: {
    title: "Catch a contradiction",
    hint: "“Velmar has three moons”",
    href: `/chat?prompt=${encodeURIComponent("Velmar has three moons that rise together at the solstice.")}`,
  },
  myth: { title: "Save a myth", hint: "Keep a clash as in-world lore", href: "/review" },
};

/** The signed-in Home page: what waits for the author, their worlds, credits and canon at a glance. */
export function Dashboard() {
  const { world, worlds, isLoading, error } = useWorld();
  const me = useMe();

  if (error) {
    return (
      <main className="px-4 py-6 md:px-6">
        <p role="alert" className="m-0 text-conflict">
          Could not load your worlds. Is the Sagaloom API running?
        </p>
      </main>
    );
  }
  if (isLoading || !world) {
    return (
      <main className="px-4 py-6 md:px-6">
        <p className={MUTED}>{isLoading ? "Loading your worlds…" : "Setting up your world…"}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-[1680px] flex-1 flex-col gap-[18px] px-4 py-[18px] md:px-6">
      <h1 className="sr-only">Home</h1>
      {world.is_demo && me && <FirstSteps userId={me.id} />}
      <div className="grid flex-1 grid-cols-1 items-stretch gap-[18px] lg:grid-cols-3">
        <WorldsPanel world={world} worlds={worlds} me={me} />
        <DecisionsPanel world={world} />
        <CanonPanel world={world} />
      </div>
    </main>
  );
}

/** The Get Started checklist as a slim row of cards; gone once done or hidden. */
function FirstSteps({ userId }: { userId: string }) {
  const tour = useTour(userId);
  if (!tour.ready || tour.dismissed) return null;
  const done = TOUR_STEPS.filter((s) => tour.done[s]).length;
  if (done === TOUR_STEPS.length) return null;
  const next = TOUR_STEPS.find((s) => !tour.done[s]);

  return (
    <section
      aria-labelledby="home-start"
      className="flex flex-wrap items-stretch gap-3 rounded-[14px] border border-border bg-panel p-3"
    >
      <div className="flex min-w-[170px] flex-[0_1_200px] flex-col justify-center gap-1.5 px-1.5">
        <h2 id="home-start" className="m-0 font-heading text-xl font-medium">
          Get started
        </h2>
        <div
          role="progressbar"
          aria-label="Get started progress"
          aria-valuemin={0}
          aria-valuemax={TOUR_STEPS.length}
          aria-valuenow={done}
          className="h-[5px] overflow-hidden rounded-full bg-border"
        >
          <div className="h-full bg-accent" style={{ width: `${(done / TOUR_STEPS.length) * 100}%` }} />
        </div>
        <span className="text-xs text-muted-foreground">
          {done} of {TOUR_STEPS.length} done ·{" "}
          <button
            type="button"
            onClick={() => markTour("dismissed")}
            className="cursor-pointer border-0 bg-transparent p-0 text-xs text-muted-foreground underline hover:text-foreground"
          >
            Hide
          </button>
        </span>
      </div>
      <ol className="m-0 grid flex-1 list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 xl:grid-cols-4">
        {TOUR_STEPS.map((step) => {
          const card = TOUR_CARDS[step];
          const isDone = tour.done[step];
          const status = isDone ? "Done" : step === next ? "Next" : "To do";
          return (
            <li key={step} className="flex">
              <Link
                href={card.href}
                className={`flex flex-1 items-center gap-3 rounded-[10px] border px-3.5 py-2.5 text-foreground no-underline hover:bg-panel-3 hover:no-underline hover:text-foreground ${
                  step === next ? "border-conflict-line bg-conflict-bg" : "border-border-strong bg-raised"
                } ${isDone ? "opacity-65" : ""}`}
              >
                <span className="flex flex-1 flex-col">
                  <span className="text-sm font-semibold">{card.title}</span>
                  <span className="text-xs text-prose-muted">{card.hint}</span>
                </span>
                <span
                  className={`text-[11px] font-semibold uppercase ${
                    isDone ? "text-accent" : step === next ? "text-conflict" : "text-muted-foreground"
                  }`}
                >
                  {isDone ? "✓ Done" : status}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function WorldsPanel({ world, worlds, me }: { world: World; worlds: World[]; me: Me | undefined }) {
  const { setWorldId, startWorld } = useWorld();
  const threads = useQuery({ queryKey: ["threads"], queryFn: getThreads });
  const entries = useQuery({ queryKey: ["entries", world.id], queryFn: () => getEntries(world.id) });
  const stats = worldStats(threads.data ?? []);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [failed, setFailed] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setCreating(true);
    setFailed(false);
    try {
      await startWorld(trimmed);
      setNaming(false);
      setName("");
    } catch {
      setFailed(true);
    } finally {
      setCreating(false);
    }
  }

  return (
    <section aria-labelledby="home-worlds" className={PANEL}>
      <h2 id="home-worlds" className={H2}>
        My worlds
      </h2>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {worlds.map((w) => {
          const s = stats.get(w.id);
          const current = w.id === world.id;
          const parts: ReactNode[] = [];
          if (current && entries.data) parts.push(`${entries.data.length} entries`);
          if (threads.data) parts.push(`${s?.chats ?? 0} ${s?.chats === 1 ? "chat" : "chats"}`);
          return (
            <li key={w.id}>
              <button
                type="button"
                onClick={() => setWorldId(w.id)}
                aria-current={current ? "true" : undefined}
                className={`${ROW} w-full cursor-pointer text-left ${current ? "border-border-strong bg-raised" : ""}`}
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold">{w.name}</span>
                  {w.is_demo && (
                    <span className="rounded-[5px] border border-border-strong px-1.5 text-[10px] tracking-[1px] text-muted-foreground">
                      SAMPLE
                    </span>
                  )}
                  {current && (
                    <span className="rounded-[5px] bg-accent px-1.5 text-[10px] font-semibold tracking-[1px] text-accent-foreground">
                      CURRENT
                    </span>
                  )}
                </span>
                <span className="text-xs text-muted-foreground">
                  {parts.join(" · ")}
                  {s && s.waiting > 0 && (
                    <span className="text-conflict">
                      {parts.length > 0 ? " · " : ""}
                      {s.waiting} waiting
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {naming ? (
        <form onSubmit={create} className="flex flex-wrap gap-2">
          <label htmlFor="home-new-world" className="sr-only">
            New world name
          </label>
          <input
            id="home-new-world"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="World name"
            className="min-h-11 min-w-0 flex-1 rounded-[10px] border border-border-strong bg-well px-3 text-sm text-foreground"
          />
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="min-h-11 rounded-[10px] bg-accent px-4 text-[13px] font-semibold text-accent-foreground disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={() => setNaming(false)}
            className="min-h-11 rounded-[10px] border border-border-strong px-3 text-[13px] text-foreground"
          >
            Cancel
          </button>
          {failed && (
            <p role="alert" className="m-0 w-full text-[13px] text-conflict">
              Could not create the world. Try again.
            </p>
          )}
        </form>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setNaming(true)}
            className="min-h-11 cursor-pointer rounded-[10px] border border-dashed border-border-strong bg-transparent text-[13px] font-semibold text-foreground hover:bg-panel-3"
          >
            + New world
          </button>
          <Link
            href="/import"
            className="flex min-h-11 items-center justify-center rounded-[10px] border border-border bg-panel-2 text-[13px] text-foreground no-underline hover:bg-panel-3 hover:no-underline hover:text-foreground"
          >
            Import notes
          </Link>
        </div>
      )}
      <RecentlyAdded world={world} entries={entries.data} />
      <CreditsBox me={me} />
    </section>
  );
}

function RecentlyAdded({ world, entries }: { world: World; entries: Entry[] | undefined }) {
  const [showSecrets] = useShowSecrets(world.id);
  if (!entries || entries.length === 0) return null;
  return (
    <>
      <h3 className="m-0 mt-2 text-[15px] font-semibold">Recently added to canon</h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {newestFirst(entries, 3).map((e) => {
          const hidden = e.status === "secret" && !showSecrets;
          return (
            <li key={e.id}>
              <Link
                href={`/canon/${encodeURIComponent(e.id)}`}
                className="flex items-center gap-2.5 rounded-[10px] border border-border bg-panel-2 px-3 py-2 text-[13px] text-foreground no-underline hover:bg-panel-3 hover:no-underline hover:text-foreground"
              >
                <span className={`w-[76px] shrink-0 text-[10px] uppercase tracking-[1px] ${TYPE_CLASS[e.type]}`}>
                  {e.type}
                </span>
                <span className="min-w-0 flex-1 truncate">{hidden ? "Hidden secret entry" : e.title}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{ago(e.created_at)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function CreditsBox({ me }: { me: Me | undefined }) {
  return (
    <section
      aria-labelledby="home-credits"
      className={`mt-auto flex flex-col gap-2 rounded-[10px] border bg-panel-2 p-3.5 ${
        me?.over_budget ? "border-conflict" : "border-border"
      }`}
    >
      <div className="flex items-baseline gap-2">
        <h3 id="home-credits" className="m-0 flex-1 text-sm font-semibold">
          AI credits this month
        </h3>
        {me && <span className="text-xs text-muted-foreground">resets {resetDay(me.budget_resets_on)}</span>}
      </div>
      {me ? <CreditsBody me={me} /> : <p className={MUTED}>Loading…</p>}
    </section>
  );
}

function CreditsBody({ me }: { me: Me }) {
  const c = credits(me);
  return (
    <>
      {c.usedPercent !== null && (
        <div
          role="progressbar"
          aria-label="AI budget used"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(c.usedPercent)}
          className="h-[7px] overflow-hidden rounded-full bg-border"
        >
          <div
            className={`h-full ${c.over ? "bg-conflict" : "bg-accent"}`}
            style={{ width: `${c.usedPercent}%` }}
          />
        </div>
      )}
      <p className="m-0 text-xs text-prose-muted">
        <span className={`font-heading text-xl ${c.over ? "text-conflict" : "text-foreground"}`}>{c.headline}</span>{" "}
        {c.detail}
      </p>
    </>
  );
}

function DecisionsPanel({ world }: { world: World }) {
  const review = useQuery({
    queryKey: REVIEW_KEY(world.id),
    queryFn: () => getReviewThreads(world.id),
    refetchInterval: (q) => reviewPollMs(q.state.data),
  });
  const rows = review.data ?? [];
  const total = rows.reduce((n, t) => n + t.pending, 0);

  return (
    <section aria-labelledby="home-decide" className={PANEL}>
      <div className="flex items-center gap-2">
        <h2 id="home-decide" className={`${H2} flex-1`}>
          Needs your decision
          {total > 0 && (
            <span className="ml-1.5 rounded-full bg-conflict px-[7px] py-px text-[11px] font-semibold text-accent-foreground">
              {total}
            </span>
          )}
        </h2>
        <Link href="/review" className="text-[13px]">
          Open Review →
        </Link>
      </div>
      {review.isError && (
        <p role="alert" className="m-0 text-[13px] text-conflict">
          Could not load the review queue.
        </p>
      )}
      {review.isPending && <p className={MUTED}>Loading…</p>}
      {review.data && rows.length === 0 && (
        <p className="m-0 font-heading text-[16px] text-prose-muted">
          Nothing waiting. Every change the assistant proposes waits here until you decide.
        </p>
      )}
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {rows.slice(0, 5).map((t) => (
          <li key={t.thread_id}>
            <Link href={`/review/${encodeURIComponent(t.thread_id)}`} className={ROW}>
              <span className="flex items-center gap-1.5">
                {t.badge && (
                  <span className={`rounded-full px-2 py-px text-[11px] font-semibold ${BADGE_CLASS[t.badge]}`}>
                    {BADGE_LABEL[t.badge]}
                  </span>
                )}
                <span className="flex-1" />
                <span className="text-[11px] text-muted-foreground">{ago(t.created_at)}</span>
              </span>
              <span className="text-sm font-semibold">
                {t.title ?? (t.kind === "import" ? "Untitled import" : "Untitled chat")}
              </span>
              <span className="text-xs text-prose-muted">
                {t.kind === "import" ? "Import" : "Chat"} · {t.pending} {t.pending === 1 ? "proposal" : "proposals"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {rows.length > 5 && (
        <Link href="/review" className="text-[13px]">
          {rows.length - 5} more in Review →
        </Link>
      )}
      <p className="m-0 mt-auto border-t border-border pt-3 text-xs text-muted-foreground">
        Nothing enters canon until you decide.
      </p>
    </section>
  );
}

function CanonPanel({ world }: { world: World }) {
  const entries = useQuery({ queryKey: ["entries", world.id], queryFn: () => getEntries(world.id) });
  const threads = useQuery({ queryKey: ["threads"], queryFn: getThreads });
  const h = entries.data ? canonHealth(entries.data) : null;
  const chats = threads.data ? recentChats(threads.data, world.id) : [];
  // Each tile opens Canon filtered to what it counts (lib/canonFilter.ts); "entries" opens the whole list.
  const tiles: { n: number | undefined; label: string; cls: string; href: string }[] = [
    { n: h?.entries, label: h?.entries === 1 ? "entry" : "entries", cls: "text-foreground", href: canonHref(null) },
    { n: h?.myths, label: h?.myths === 1 ? "myth" : "myths", cls: "text-myth", href: canonHref("myth") },
    { n: h?.rumours, label: h?.rumours === 1 ? "rumour" : "rumours", cls: "text-event", href: canonHref("rumour") },
    { n: h?.secrets, label: h?.secrets === 1 ? "secret" : "secrets", cls: "text-foreground", href: canonHref("secret") },
  ];

  return (
    <section aria-labelledby="home-health" className={PANEL}>
      <h2 id="home-health" className={H2}>
        Canon health
      </h2>
      {entries.isError ? (
        <p role="alert" className="m-0 text-[13px] text-conflict">
          Could not load this world&apos;s canon.
        </p>
      ) : (
        <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0">
          {tiles.map((t) => (
            <li key={t.href}>
              <Link
                href={t.href}
                className="flex flex-col rounded-[10px] border border-border bg-panel-2 px-3 py-2.5 text-foreground no-underline hover:border-border-strong hover:bg-panel-3 hover:text-foreground hover:no-underline"
              >
                <span className={`font-heading text-2xl ${t.cls}`}>{t.n ?? "…"}</span>{" "}
                <span className="text-xs text-muted-foreground">{t.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-1 flex items-center">
        <h2 className={`${H2} flex-1`}>Recent chats</h2>
        <Link href="/chat" className="text-[13px]">
          + New chat
        </Link>
      </div>
      {threads.isPending && <p className={MUTED}>Loading…</p>}
      {threads.data && chats.length === 0 && <p className={MUTED}>No chats in {world.name} yet.</p>}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {chats.map((t) => (
          <li key={t.thread_id}>
            <Link
              href={`/chat/${encodeURIComponent(t.thread_id)}`}
              className="block rounded-[10px] border border-border bg-panel-2 px-3.5 py-2.5 text-[13px] text-foreground no-underline hover:bg-panel-3 hover:no-underline hover:text-foreground"
            >
              {t.title ?? "Untitled chat"} <span className="text-xs text-muted-foreground">· {ago(t.created_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
