"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { createWorld, getWorlds } from "./api";
import type { World } from "./types";

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
  const query = useQuery({ queryKey: ["worlds"], queryFn: getWorlds });
  const [storedId, setStoredId] = useState<string | null>(readStoredWorld);
  const [threadId, setThreadId] = useState<string | null>(null);

  const worlds = useMemo(() => query.data ?? [], [query.data]);
  const world = worlds.find((w) => w.id === storedId) ?? worlds[0] ?? null;

  const setWorldId = useCallback((id: string) => {
    setStoredId(id);
    setThreadId(null);
    try {
      localStorage.setItem(WORLD_KEY, id);
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }, []);

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
    isLoading: query.isLoading,
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
