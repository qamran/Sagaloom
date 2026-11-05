"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { getThread } from "@/lib/api";
import { useCourseNotes } from "@/lib/courseNotes";
import { useWorld } from "@/lib/world";

const NEW_WORLD = "__new__";

const TABS = [
  { href: "/canon", label: "Canon" },
  { href: "/chat", label: "Chat" },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#6FBFA8"
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

export function Header() {
  const pathname = usePathname();
  return (
    <header className="flex flex-wrap items-center gap-x-[18px] gap-y-2.5 border-b border-border bg-panel px-5 py-2.5">
      <Link href="/canon" className="no-underline hover:no-underline">
        <Logo />
      </Link>
      <WorldPicker />
      <nav aria-label="Main" className="flex gap-1 rounded-[10px] border border-border bg-[#1a1f1d] p-1">
        {TABS.map((t) => {
          const active = pathname === t.href || pathname.startsWith(`${t.href}/`);
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-11 items-center rounded-[7px] px-3.5 text-[13px] no-underline hover:no-underline sm:min-h-8 ${
                active
                  ? "bg-accent font-semibold text-accent-foreground hover:text-accent-foreground"
                  : "text-foreground hover:text-foreground hover:bg-panel-3"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      <div className="hidden flex-1 sm:block" />
      <CostPill />
      <CourseNotesToggle />
      <div className="flex items-center gap-2 sm:border-l sm:border-border sm:pl-4">
        <span className="text-[10px] uppercase tracking-[1.2px] text-muted-foreground">
          Developer
        </span>
        <Link
          href="/studio"
          aria-current={pathname.startsWith("/studio") ? "page" : undefined}
          className={`flex min-h-11 items-center rounded-[7px] border border-[#5b4785] px-[13px] text-[13px] no-underline hover:no-underline sm:min-h-9 ${
            pathname.startsWith("/studio")
              ? "border-myth bg-myth font-semibold text-background hover:text-background"
              : "text-myth hover:bg-[#211c33] hover:text-myth"
          }`}
        >
          Studio
        </Link>
      </div>
    </header>
  );
}
