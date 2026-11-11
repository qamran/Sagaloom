"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ACCOUNT_UNAVAILABLE, handleAuthStatus, PROXY_BASE, SESSION_REJECTED } from "./api";
import { detailOf, readEvents } from "./readSse";
import type { SseEvent } from "./types";

/** What an import sends: pasted or uploaded text, or the page URLs of a fan wiki. */
export type ImportBody = { text: string; filename?: string } | { kind: "wiki"; urls: string[] };

export type ImportPhase = "idle" | "extracting" | "checking" | "error";

export interface ImportRun {
  phase: ImportPhase;
  /** Proposals the extraction found, and candidates left out; null until the extraction reports. */
  candidates: number | null;
  skipped: number | null;
  /** The run's `node`, `llm_*`, `tool_result`, `interrupt` and `usage` events, for Under the hood. */
  events: SseEvent[];
  /** The world the running (or last) import writes into, so its drawer follows that world's secrets. */
  worldId: string | null;
  error: string | null;
  start: (worldId: string, body: ImportBody) => Promise<void>;
}

const UNREACHABLE = "Could not reach Sagaloom. Please try again.";
const LOST = "Lost the connection. The import may still finish: check Recent imports below.";
const NO_THREAD = "The import finished, but Sagaloom did not say which review to open. Find it under Recent imports below.";

/** Starts an import and follows its stream; on `done` it opens the new thread in Review. */
export function useImport(): ImportRun {
  const router = useRouter();
  const qc = useQueryClient();
  const [phase, setPhase] = useState<ImportPhase>("idle");
  const [candidates, setCandidates] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<number | null>(null);
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [worldId, setWorldId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // Leaving the page drops the connection; the server finishes the run on its own.
  useEffect(() => () => abortRef.current?.abort(), []);

  const start = useCallback(
    async (worldId: string, body: ImportBody) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setPhase("extracting");
      setCandidates(null);
      setSkipped(null);
      setEvents([]);
      setWorldId(worldId);
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
          res = await fetch(`${PROXY_BASE}/worlds/${encodeURIComponent(worldId)}/imports`, {
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
          const auth = handleAuthStatus(res.status, detail);
          if (auth === "redirected") return;
          if (auth === "rejected") fail(SESSION_REJECTED);
          else if (res.status === 503) fail(ACCOUNT_UNAVAILABLE);
          else if (res.status === 413) fail("That text is too large.");
          else if (res.status === 429) fail("Too many requests. Wait a moment and try again.");
          else if (res.status === 422) fail(detail || "That text was not accepted.");
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
          else fail(NO_THREAD);
        }
      } finally {
        busyRef.current = false;
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [qc, router],
  );

  return { phase, candidates, skipped, events, worldId, error, start };
}
