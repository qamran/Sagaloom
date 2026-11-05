import { useCallback, useSyncExternalStore } from "react";

export const COURSE_NOTES_KEY = "sagaloom.courseNotes";

/** Feature map card ids a course chip can point at. */
export type FeatureCardId =
  | "agent_purpose"
  | "agentic_rag"
  | "human_in_the_loop"
  | "memory"
  | "token_cost"
  | "langsmith"
  | "multi_provider"
  | "security_guard"
  | "external_tools";

const listeners = new Set<() => void>();
// Fallback for when localStorage is unavailable: the toggle still works for this page load.
let memory: boolean | null = null;

function read(): boolean {
  try {
    const v = localStorage.getItem(COURSE_NOTES_KEY);
    if (v === "true") return true;
    if (v === "false") return false;
  } catch {
    /* storage unavailable */
  }
  return memory ?? true;
}

function write(on: boolean) {
  memory = on;
  try {
    localStorage.setItem(COURSE_NOTES_KEY, String(on));
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === COURSE_NOTES_KEY || e.key === null) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

/** Whether course annotation chips show (R20.8). Every chip and the header toggle stay in sync. */
export function useCourseNotes(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, read, () => true);
  return [on, useCallback((v: boolean) => write(v), [])];
}
