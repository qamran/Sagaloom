"use client";

import { useAuth } from "@clerk/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { WorldProvider } from "@/lib/world";

const newClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

/**
 * One query cache per signed-in user. Clerk switches users without a full page load, so a shared cache
 * would show user B the previous user's worlds, spend and entries until B's own queries answered.
 * Swapping the client in the same render means no component ever reads A's data as B, and keying
 * WorldProvider by user generation (not on Clerk's first load) drops A's picked world and open thread.
 */
export function Providers({ children }: { children: ReactNode }) {
  const { isLoaded, userId } = useAuth();
  // `undefined` until Clerk has loaded; then the user id, or null when signed out.
  const [scope, setScope] = useState<{ user: string | null | undefined; client: QueryClient; generation: number }>(
    () => ({ user: undefined, client: newClient(), generation: 0 }),
  );
  const user = isLoaded ? (userId ?? null) : scope.user;
  if (user !== scope.user) {
    // Clerk finishing its first load is not a user change: keep what was fetched meanwhile.
    setScope(
      scope.user === undefined
        ? { ...scope, user }
        : { user, client: newClient(), generation: scope.generation + 1 },
    );
  }
  const { client } = scope;
  // A replaced cache is dropped, so the previous user's data does not linger in memory.
  useEffect(() => () => client.clear(), [client]);

  return (
    <QueryClientProvider client={client}>
      <WorldProvider key={scope.generation}>{children}</WorldProvider>
    </QueryClientProvider>
  );
}
