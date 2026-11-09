import { useCallback, useSyncExternalStore } from "react";
import { useWorld } from "@/lib/world";

export const SHOW_SECRETS_KEY = (worldId: string) => `sagaloom.showSecrets.${worldId}`;

const listeners = new Map<string, Set<() => void>>();
// Fallback for when sessionStorage is unavailable: the toggle still works for this page load.
const memory = new Map<string, boolean>();

function read(worldId: string): boolean {
  const key = SHOW_SECRETS_KEY(worldId);
  try {
    return sessionStorage.getItem(key) === "true";
  } catch {
    return memory.get(key) ?? false;
  }
}

function write(worldId: string, on: boolean) {
  const key = SHOW_SECRETS_KEY(worldId);
  memory.set(key, on);
  try {
    sessionStorage.setItem(key, String(on));
  } catch {
    /* storage unavailable */
  }
  listeners.get(key)?.forEach((l) => l());
}

function subscribe(worldId: string, cb: () => void) {
  const key = SHOW_SECRETS_KEY(worldId);
  const set = listeners.get(key) ?? new Set<() => void>();
  set.add(cb);
  listeners.set(key, set);
  return () => {
    set.delete(cb);
  };
}

/** Whether secrets show for a world (this tab only). Always false without a world id. */
export function useShowSecrets(worldId: string | undefined): [boolean, (on: boolean) => void] {
  const sub = useCallback((cb: () => void) => (worldId ? subscribe(worldId, cb) : () => {}), [worldId]);
  const on = useSyncExternalStore(
    sub,
    () => (worldId ? read(worldId) : false),
    () => false,
  );
  const set = useCallback(
    (v: boolean) => {
      if (worldId) write(worldId, v);
    },
    [worldId],
  );
  return [on, set];
}

/** The active world's toggle: what a masked view ORs into its hidden test. */
export function useWorldShowSecrets(): boolean {
  const { world } = useWorld();
  return useShowSecrets(world?.id)[0];
}
