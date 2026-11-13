"use client";

import { useAuth, UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { getReviewThreads, getThread } from "@/lib/api";
import { useCourseNotes } from "@/lib/courseNotes";
import { spendLine, useMe } from "@/lib/me";
import { SecretsToggle } from "@/components/SecretsToggle";
import { TipsDialog } from "@/components/TipsDialog";
import { REVIEW_KEY, reviewPollMs } from "@/lib/review";
import { useWorld } from "@/lib/world";

const NEW_WORLD = "__new__";

const TABS = [
  { href: "/home", label: "Home" },
  { href: "/canon", label: "Canon" },
  { href: "/chat", label: "Chat" },
  { href: "/review", label: "Review" },
  { href: "/import", label: "Import" },
  { href: "/compare", label: "Compare" },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        className="stroke-accent"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H19v15H5.5A1.5 1.5 0 0 0 4 19.5z" />
        <path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H19v-3" />
        <path d="M12 7l1 2.2 2.4.3-1.8 1.6.5 2.4-2.1-1.2-2.1 1.2.5-2.4-1.8-1.6 2.4-.3z" />
      </svg>
      <span className="font-heading text-[21px] font-semibold text-foreground">Sagaloom</span>
    </div>
  );
}

function WorldPicker() {
  const { worlds, world, setWorldId, startWorld } = useWorld();
  const router = useRouter();
  const pathname = usePathname();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await startWorld(trimmed);
      if (pathname.startsWith("/canon/")) router.push("/canon");
      setName("");
      setCreating(false);
    } catch {
      setError("Could not create the world.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor="world-picker" className="sr-only">
        World
      </label>
      <select
        id="world-picker"
        value={world?.id ?? ""}
        disabled={worlds.length === 0}
        onChange={(e) => {
          if (e.target.value === NEW_WORLD) setCreating(true);
          else {
            setWorldId(e.target.value);
            if (pathname.startsWith("/canon/")) router.push("/canon");
          }
        }}
        className="min-h-11 rounded-lg border border-border bg-panel-3 px-3 text-[13px] text-foreground sm:min-h-9"
      >
        {worlds.length === 0 && <option value="">Loading worlds…</option>}
        {worlds.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name}
          </option>
        ))}
        <option value={NEW_WORLD}>+ New world</option>
      </select>
      {creating && (
        <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
          <label htmlFor="new-world-name" className="sr-only">
            New world name
          </label>
          <input
            id="new-world-name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="World name"
            maxLength={80}
            className="min-h-11 w-40 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground sm:min-h-9"
          />
          <button
            type="submit"
            disabled={busy || !name.trim()}
            className="min-h-11 rounded-lg bg-accent px-3 text-[13px] font-semibold text-accent-foreground disabled:opacity-50 sm:min-h-9"
          >
            Create
          </button>
          <button
            type="button"
            onClick={() => setCreating(false)}
            className="min-h-11 rounded-lg border border-border-strong px-3 text-[13px] text-foreground sm:min-h-9"
          >
            Cancel
          </button>
          {error && (
            <span role="alert" className="text-xs text-conflict">
              {error}
            </span>
          )}
        </form>
      )}
    </div>
  );
}

function CostPill() {
  const { threadId } = useWorld();
  const { data } = useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => getThread(threadId as string),
    enabled: threadId !== null,
  });
  if (!threadId || !data) return null;
  const tokens = data.usage.prompt_tokens + data.usage.completion_tokens;
  return (
    <div
      aria-label="Session cost"
      className="rounded-full border border-border px-3 py-[5px] text-xs text-muted-foreground"
    >
      {tokens.toLocaleString("en-US")} tokens ·{" "}
      <span className="text-foreground">${data.usage.cost_usd.toFixed(4)}</span>
    </div>
  );
}

/** Proposals waiting for a decision in the active world; nothing while there are none. */
function ReviewCount() {
  const { world } = useWorld();
  const { data } = useQuery({
    queryKey: REVIEW_KEY(world?.id ?? ""),
    queryFn: () => getReviewThreads(world?.id as string),
    enabled: !!world,
    refetchInterval: (q) => reviewPollMs(q.state.data),
  });
  const count = data?.reduce((n, t) => n + t.pending, 0) ?? 0;
  if (!count) return null;
  return (
    <>
      {" "}
      <span className="ml-1 rounded-full bg-background px-1.5 text-[11px] font-semibold text-conflict">{count}</span>
      {" "}
      <span className="sr-only">pending</span>
    </>
  );
}

function CourseNotesToggle() {
  const [on, setOn] = useCourseNotes();
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => setOn(!on)}
      className={`min-h-11 rounded-lg border px-3 text-[13px] sm:min-h-9 ${
        on ? "border-myth text-myth" : "border-border-strong text-muted-foreground"
      }`}
    >
      Course notes
    </button>
  );
}

/** This month's AI spend against the budget (the admin has none); updates after every turn. */
function SpendLine() {
  const me = useMe();
  if (!me) return null;
  return (
    <div
      data-testid="spend-line"
      className={`rounded-full border px-3 py-[5px] text-xs ${
        me.over_budget ? "border-conflict text-conflict-text" : "border-border text-muted-foreground"
      }`}
    >
      {spendLine(me)}
    </div>
  );
}

// From tablet width up the header stays at the top while the page scrolls. On a phone it wraps to
// several rows, so it scrolls away there instead of covering the screen.
const HEADER =
  "z-40 flex flex-wrap items-center gap-x-[18px] gap-y-2.5 border-b border-border bg-panel px-5 py-2.5 md:sticky md:top-0";
const AUTH_LINK =
  "flex min-h-11 items-center rounded-lg px-3.5 text-[13px] no-underline hover:no-underline sm:min-h-9";

/** The page header. It publishes its height as `--header-h` on <html>, so sticky columns sit below
 * it and in-page links (`scroll-padding-top` in globals.css) land under it, not behind it; the
 * height changes when the header wraps to a second row. */
function HeaderBar({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement;
    const publish = () =>
      root.style.setProperty("--header-h", `${el.offsetHeight}px`);
    publish();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(publish);
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      root.style.removeProperty("--header-h");
    };
  }, []);
  return (
    <header ref={ref} className={HEADER}>
      {children}
    </header>
  );
}

export function Header() {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded || !isSignedIn) {
    return (
      <HeaderBar>
        <Link href="/" className="no-underline hover:no-underline">
          <Logo />
        </Link>
        <div className="flex-1" />
        {isLoaded && (
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className={`${AUTH_LINK} border border-border-strong text-foreground hover:text-foreground`}>
              Sign in
            </Link>
            <Link href="/sign-up" className={`${AUTH_LINK} bg-accent font-semibold text-accent-foreground hover:text-accent-foreground`}>
              Sign up free
            </Link>
          </div>
        )}
      </HeaderBar>
    );
  }
  return <SignedInHeader />;
}

function SignedInHeader() {
  const pathname = usePathname();
  return (
    <HeaderBar>
      <Link href="/home" className="no-underline hover:no-underline">
        <Logo />
      </Link>
      <WorldPicker />
      {/* Six tabs are wider than a phone: the tab row scrolls on its own instead of the page. */}
      <nav
        aria-label="Main"
        className="flex max-w-full gap-1 overflow-x-auto rounded-[10px] border border-border bg-raised p-1"
      >
        {TABS.map((t) => {
          const active = pathname === t.href || pathname.startsWith(`${t.href}/`);
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-11 shrink-0 items-center rounded-[7px] px-3.5 text-[13px] no-underline hover:no-underline sm:min-h-8 ${
                active
                  ? "bg-accent font-semibold text-accent-foreground hover:text-accent-foreground"
                  : "text-foreground hover:text-foreground hover:bg-panel-3"
              }`}
            >
              {t.label}
              {t.href === "/review" && <ReviewCount />}
            </Link>
          );
        })}
      </nav>
      <div className="hidden flex-1 sm:block" />
      <CostPill />
      <SpendLine />
      <SecretsToggle />
      <CourseNotesToggle />
      {/* One "Developer studio" tab, set apart by the divider and its violet style (R20.4: developer
          settings kept apart from the author's screens). */}
      <div className="flex items-center sm:border-l sm:border-border sm:pl-4">
        <Link
          href="/studio"
          aria-current={pathname.startsWith("/studio") ? "page" : undefined}
          className={`flex min-h-11 items-center rounded-[7px] border border-violet-line-strong px-[13px] text-[13px] no-underline hover:no-underline sm:min-h-9 ${
            pathname.startsWith("/studio")
              ? "border-myth bg-myth font-semibold text-background hover:text-background"
              : "text-myth hover:bg-myth-bg hover:text-myth"
          }`}
        >
          Developer studio
        </Link>
      </div>
      <UserButton />
      <TipsDialog />
    </HeaderBar>
  );
}
