"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { createWorld, getMe, getWorlds, putMe } from "./api";
import { ME_KEY } from "./me";
import { setTourUser } from "./tour";
import type { Me, World } from "./types";

const WORLD_KEY = "sagaloom.world";

function readStoredWorld(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(WORLD_KEY);
  } catch {
    return null;
  }
}

interface WorldContextValue {
  worlds: World[];
  /** The active world; defaults to the first one (Velmar on first run). */
  world: World | null;
  isLoading: boolean;
  error: Error | null;
  setWorldId: (id: string) => void;
  /** Creates an empty world alongside the others and switches to it (R10.5). */
  startWorld: (name: string) => Promise<World>;
  /** The chat thread whose usage the header shows; Chat sets it. */
  threadId: string | null;
  setThreadId: (id: string | null) => void;
}

const WorldContext = createContext<WorldContextValue | null>(null);

export function WorldProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { isSignedIn } = useAuth();
  const query = useQuery({ queryKey: ["worlds"], queryFn: getWorlds, enabled: !!isSignedIn });
  const meQuery = useQuery({ queryKey: ME_KEY, queryFn: getMe, enabled: !!isSignedIn });
  // The author's own pick this session; before one, the account's last world, then this browser's.
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [storedId] = useState<string | null>(readStoredWorld);
  const [threadId, setThreadId] = useState<string | null>(null);

  const worlds = useMemo(() => query.data ?? [], [query.data]);
  // The Get Started flags are per user; set before any child reads them.
  setTourUser(meQuery.data?.id ?? null);
  // Wait for /me (when it is coming) so the first world is the remembered one, not a flash of another.
  const meSettled = !isSignedIn || meQuery.isFetched;
  const lastId = meQuery.data?.last_world_id;
  const known = (id: string | null | undefined) => worlds.find((w) => w.id === id);
  const world = meSettled ? (known(pickedId) ?? known(lastId) ?? known(storedId) ?? worlds[0] ?? null) : null;

  const setWorldId = useCallback((id: string) => {
    setPickedId(id);
    setThreadId(null);
    qc.setQueryData<Me>(ME_KEY, (m) => (m ? { ...m, last_world_id: id } : m));
    // The server's copy is only a memory for the next visit: a failed save must not block the switch.
    putMe(id).catch(() => undefined);
    try {
      localStorage.setItem(WORLD_KEY, id);
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }, [qc]);

  const startWorld = useCallback(
    async (name: string) => {
      const created = await createWorld(name);
      await qc.invalidateQueries({ queryKey: ["worlds"] });
      setWorldId(created.id);
      return created;
    },
    [qc, setWorldId],
  );

  const value: WorldContextValue = {
    worlds,
    world,
    isLoading: query.isLoading || !meSettled,
    error: query.error,
    setWorldId,
    startWorld,
    threadId,
    setThreadId,
  };
  return <WorldContext.Provider value={value}>{children}</WorldContext.Provider>;
}

export function useWorld(): WorldContextValue {
  const ctx = useContext(WorldContext);
  if (!ctx) throw new Error("useWorld must be used inside <WorldProvider>");
  return ctx;
}
