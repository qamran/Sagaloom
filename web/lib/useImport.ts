"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { detailOf, readEvents } from "./readSse";
import type { SseEvent } from "./types";

export type ImportPhase = "idle" | "extracting" | "checking" | "error";

export interface ImportRun {
  phase: ImportPhase;
  /** Proposals the extraction found, and candidates left out; null until the extraction reports. */
  candidates: number | null;
  skipped: number | null;
  /** The run's `node`, `llm_*`, `tool_result`, `interrupt` and `usage` events, for Under the hood. */
  events: SseEvent[];
  error: string | null;
  start: (worldId: string, body: { text: string; filename?: string }) => Promise<void>;
}

const UNREACHABLE = "Could not reach Sagaloom. Please try again.";
const LOST = "Lost the connection. The import may still finish: check Recent imports below.";

/** Starts an import and follows its stream; on `done` it opens the new thread in Review. */
export function useImport(): ImportRun {
  const router = useRouter();
  const qc = useQueryClient();
  const [phase, setPhase] = useState<ImportPhase>("idle");
  const [candidates, setCandidates] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<number | null>(null);
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // Leaving the page drops the connection; the server finishes the run on its own.
  useEffect(() => () => abortRef.current?.abort(), []);

  const start = useCallback(
    async (worldId: string, body: { text: string; filename?: string }) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setPhase("extracting");
      setCandidates(null);
      setSkipped(null);
      setEvents([]);
      setError(null);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const fail = (message: string) => {
        setPhase("error");
        setError(message);
      };
      try {
        let res: Response;
        try {
          res = await fetch(`/api/proxy/worlds/${encodeURIComponent(worldId)}/imports`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify(body),
            signal: ctrl.signal,
          });
        } catch {
          if (!ctrl.signal.aborted) fail(UNREACHABLE);
          return;
        }
        if (!res.ok || !res.body) {
          const detail = await detailOf(res);
          if (res.status === 413) fail("That text is too large.");
          else if (res.status === 429) fail("Too many requests. Wait a moment and try again.");
          else if (res.status === 422) fail(detail || "That text was not accepted.");
          else if (res.status === 409 && detail === "turn in progress") fail("An import is still running. Wait for it to finish.");
          else fail(UNREACHABLE);
          return;
        }

        let threadId: string | null = null;
        const ended = await readEvents(res, (ev) => {
          switch (ev.event) {
            case "done":
              threadId = ev.data.thread_id ?? null;
              break;
            case "error":
              fail(ev.data.message);
              break;
            case "node":
              if (ev.data.name === "check" && ev.data.phase === "start") setPhase("checking");
              setEvents((all) => [...all, ev]);
              break;
            case "tool_result":
              if (ev.data.name === "extract") {
                setCandidates(ev.data.candidates ?? 0);
                setSkipped(ev.data.skipped ?? 0);
              }
              setEvents((all) => [...all, ev]);
              break;
            case "token":
              break;
            default:
              setEvents((all) => [...all, ev]);
          }
        });
        if (ctrl.signal.aborted) return;
        if (ended === null) fail(LOST);
        else if (ended === "done") {
          void qc.invalidateQueries({ queryKey: ["review"] });
          void qc.invalidateQueries({ queryKey: ["imports"] });
          if (threadId) router.push(`/review/${encodeURIComponent(threadId)}`);
          else fail(LOST);
        }
      } finally {
        busyRef.current = false;
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [qc, router],
  );

  return { phase, candidates, skipped, events, error, start };
}
