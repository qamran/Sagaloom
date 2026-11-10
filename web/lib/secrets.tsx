import { createContext, useCallback, useContext, useSyncExternalStore, type ReactNode } from "react";
import { useWorld } from "@/lib/world";

export const SHOW_SECRETS_KEY = (worldId: string) => `sagaloom.showSecrets.${worldId}`;

const listeners = new Map<string, Set<() => void>>();
// Kept only while the last write to sessionStorage failed, and wins over storage while kept, so a
// failed "off" never reads back a stored "on". A successful write clears it.
const memory = new Map<string, boolean>();

function read(worldId: string): boolean {
  const key = SHOW_SECRETS_KEY(worldId);
  const kept = memory.get(key);
  if (kept !== undefined) return kept;
  try {
    return sessionStorage.getItem(key) === "true";
  } catch {
    return false;
  }
}

function write(worldId: string, on: boolean) {
  const key = SHOW_SECRETS_KEY(worldId);
  try {
    sessionStorage.setItem(key, String(on));
    memory.delete(key);
  } catch {
    memory.set(key, on);
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
    if (set.size === 0 && listeners.get(key) === set) listeners.delete(key);
  };
}

/** How many worlds have a live listener (for tests: a world's set goes when its last one leaves). */
export const listenedWorldCount = () => listeners.size;

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

const SecretsWorldContext = createContext<string | undefined>(undefined);

/** Scopes masked views inside to the world their content belongs to, not the active one. */
export function SecretsWorldProvider({ worldId, children }: { worldId: string; children: ReactNode }) {
  return <SecretsWorldContext.Provider value={worldId}>{children}</SecretsWorldContext.Provider>;
}

/** The content world's toggle (the active world's without a provider): what a masked view ORs into its hidden test. */
export function useWorldShowSecrets(): boolean {
  const scoped = useContext(SecretsWorldContext);
  const { world } = useWorld();
  return useShowSecrets(scoped ?? world?.id)[0];
}
