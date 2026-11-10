import { useCallback, useSyncExternalStore } from "react";

export const COURSE_NOTES_KEY = "sagaloom.courseNotes";

/** Feature map card ids a course chip can point at. */
export type FeatureCardId =
  | "agent_purpose"
  | "agentic_rag"
  | "human_in_the_loop"
  | "router"
  | "memory"
  | "token_cost"
  | "langsmith"
  | "multi_provider"
  | "security_guard"
  | "external_tools"
  | "official_canon_licence"
  | "injection_safe_extraction";

const listeners = new Set<() => void>();
// Kept only while the last write to localStorage failed, and wins over storage while kept, so a
// failed toggle never reads back the stored value. A successful write clears it.
let memory: boolean | null = null;

function read(): boolean {
  if (memory !== null) return memory;
  try {
    return localStorage.getItem(COURSE_NOTES_KEY) !== "false";
  } catch {
    return true;
  }
}

function write(on: boolean) {
  try {
    localStorage.setItem(COURSE_NOTES_KEY, String(on));
    memory = null;
  } catch {
    memory = on;
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
