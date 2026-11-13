import { useEffect, useState } from "react";

// Get Started checklist flags (design 4.3). Step 1 is set by the entry page; Task 11 sets 2-4.
// Keys carry the signed-in user's id (`sagaloom.tour.<userId>.<step>`), so two accounts in one browser
// keep separate checklists. Before the id is known (and in tests that never set it) there is no id part.
let tourUser: string | null = null;

export function setTourUser(id: string | null): void {
  tourUser = id;
}

const key = (step: string) => (tourUser ? `sagaloom.tour.${tourUser}.${step}` : `sagaloom.tour.${step}`);

export const TOUR_KEYS = {
  get visited() {
    return key("visited");
  },
  get chatted() {
    return key("chatted");
  },
  get conflict() {
    return key("conflict");
  },
  get myth() {
    return key("myth");
  },
  get dismissed() {
    return key("dismissed");
  },
};

export type TourStep = "visited" | "chatted" | "conflict" | "myth";

export const TOUR_EVENT = "sagaloom:tour";

export function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function markTour(step: TourStep | "dismissed"): void {
  try {
    localStorage.setItem(TOUR_KEYS[step], "1");
  } catch {
    /* storage unavailable: the checklist just will not tick */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(TOUR_EVENT));
}

export const TOUR_STEPS: readonly TourStep[] = ["visited", "chatted", "conflict", "myth"];

export interface TourState {
  /** False until read in the browser. */
  ready: boolean;
  dismissed: boolean;
  done: Record<TourStep, boolean>;
}

const NOT_READ: TourState = {
  ready: false,
  dismissed: false,
  done: { visited: false, chatted: false, conflict: false, myth: false },
};

export function readTour(): TourState {
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

/**
 * The checklist's live state. Pass the signed-in user's id: the keys carry it, so the flags are read
 * again once it is known (WorldProvider sets it with setTourUser when /me loads).
 */
export function useTour(userId?: string | null): TourState {
  const [tour, setTour] = useState<TourState>(NOT_READ);
  useEffect(() => {
    const sync = () => setTour(readTour());
    sync();
    window.addEventListener(TOUR_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(TOUR_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, [userId]);
  return tour;
}
