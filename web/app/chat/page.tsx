"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createThread } from "@/lib/api";
import { useWorld } from "@/lib/world";

/** Starts a thread for the active world, then moves to /chat/[threadId] (R18.6). */
export default function NewChat() {
  const { world, isLoading, error: worldError } = useWorld();
  const router = useRouter();
  const started = useRef<string | null>(null); // StrictMode runs effects twice in dev
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!world || started.current === world.id) return;
    started.current = world.id;
    createThread(world.id).then(
      ({ thread_id }) => router.replace(`/chat/${encodeURIComponent(thread_id)}`),
      () => setFailed(true),
    );
  }, [world, router]);

  return (
    <main className="px-4 py-6 md:px-11 md:py-[30px]">
      {failed || (!isLoading && (worldError || !world)) ? (
        <p role="alert" className="text-conflict">
          Could not start a chat. Is the Sagaloom API running?
        </p>
      ) : (
        <p className="text-muted-foreground">Starting a new chat…</p>
      )}
    </main>
  );
}
