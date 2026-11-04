"use client";

import { useEffect, useState } from "react";
import { markTour, readFlag, TOUR_EVENT, TOUR_KEYS, type TourStep } from "@/lib/tour";
import type { World } from "@/lib/types";

export { TOUR_KEYS } from "@/lib/tour";

const STEPS: { step: TourStep; label: string }[] = [
  { step: "visited", label: "Browse an entry (try Sky of Velmar)" },
  { step: "chatted", label: "Ask a question in Chat" },
  { step: "conflict", label: "Add a fact that breaks canon: “Velmar has three moons”" },
  { step: "myth", label: "Resolve it by saving it as a myth" },
];

interface TourState {
  ready: boolean;
  dismissed: boolean;
  done: Record<TourStep, boolean>;
}

function readTour(): TourState {
  return {
    ready: true,
    dismissed: readFlag(TOUR_KEYS.dismissed),
    done: {
      visited: readFlag(TOUR_KEYS.visited),
      chatted: readFlag(TOUR_KEYS.chatted),
      conflict: readFlag(TOUR_KEYS.conflict),
      myth: readFlag(TOUR_KEYS.myth),
    },
  };
}

/** The first-run checklist (design 4.3). Only for the demo world, until dismissed. */
export function GetStarted({ world, onStartOwn }: { world: World; onStartOwn: () => void }) {
  const [tour, setTour] = useState<TourState>({
    ready: false,
    dismissed: false,
    done: { visited: false, chatted: false, conflict: false, myth: false },
  });

  useEffect(() => {
    const sync = () => setTour(readTour());
    sync();
    window.addEventListener(TOUR_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(TOUR_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  if (!world.is_demo || !tour.ready || tour.dismissed) return null;

  const count = STEPS.filter((s) => tour.done[s.step]).length;

  return (
    <section
      aria-labelledby="get-started-title"
      className="rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2
          id="get-started-title"
          className="m-0 font-heading text-lg font-semibold text-foreground"
        >
          Get started
        </h2>
        <span className="text-xs text-muted-foreground">
          {count} of {STEPS.length} done
        </span>
        <button
          type="button"
          onClick={() => markTour("dismissed")}
          className="ml-auto min-h-11 rounded-lg border border-border-strong px-3.5 text-[13px] text-foreground hover:bg-panel-3 sm:min-h-9"
        >
          Dismiss
        </button>
      </div>
      <ol className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
        {STEPS.map(({ step, label }, i) => {
          const done = tour.done[step];
          return (
            <li key={step} className="flex items-center gap-3 text-sm">
              <span
                aria-hidden="true"
                className={`flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                  done
                    ? "border-accent bg-accent text-accent-foreground"
                    : "border-border-strong text-muted-foreground"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className={done ? "text-muted-foreground line-through" : "text-foreground"}>
                {label}
              </span>
              {done && <span className="sr-only">Done</span>}
            </li>
          );
        })}
      </ol>
      <div className="mt-4 border-t border-border pt-3.5">
        <button
          type="button"
          onClick={onStartOwn}
          className="min-h-11 rounded-lg border border-accent bg-transparent px-4 text-[13px] font-semibold text-accent hover:bg-accent hover:text-accent-foreground"
        >
          Start my own world
        </button>
        <span className="ml-3 text-xs text-muted-foreground">
          Creates an empty world next to Velmar.
        </span>
      </div>
    </section>
  );
}
