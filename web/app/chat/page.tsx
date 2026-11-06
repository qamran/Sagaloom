"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createThread, getReviewThreads } from "@/lib/api";
import { useWorld } from "@/lib/world";

/**
 * Resumes the active world's thread that waits on an approval, so a pending card is never
 * orphaned; otherwise starts a new thread. Then moves to /chat/[threadId] (R5.5, R18.6).
 */
export default function NewChat() {
  const { world, isLoading, error: worldError } = useWorld();
  const router = useRouter();
  const started = useRef<string | null>(null); // StrictMode runs effects twice in dev
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!world || started.current === world.id) return;
    started.current = world.id;
    const worldId = world.id;
    (async () => {
      let threadId: string | null = null;
      try {
        threadId = (await getReviewThreads(worldId))[0]?.thread_id ?? null;
      } catch {
        /* lookup failed: start a new thread instead */
      }
      try {
        threadId ??= (await createThread(worldId)).thread_id;
        // A Studio "Try it" link carries ?prompt=; the thread page puts it in the composer.
        const prompt = new URLSearchParams(window.location.search).get("prompt");
        router.replace(`/chat/${encodeURIComponent(threadId)}${prompt ? `?prompt=${encodeURIComponent(prompt)}` : ""}`);
      } catch {
        setFailed(true);
      }
    })();
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
