"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";
import { markTipsShown, setTipsHidden, shuffled, TIPS, tipsHidden, tipsShownThisSession } from "@/lib/tips";

const ROUND =
  "flex size-10 shrink-0 items-center justify-center rounded-full border border-border-strong text-foreground hover:border-accent hover:bg-panel-3 hover:text-accent";

/** "Useful tips" at startup: random order, back and forward, and a "Don't show this again" opt-out. */
export function TipsDialog() {
  const { userId } = useAuth();
  const [tips, setTips] = useState<string[] | null>(null);
  const [index, setIndex] = useState(0);
  const [dontShow, setDontShow] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Decided after mount: storage and the shuffle exist only in the browser.
  useEffect(() => {
    if (!userId || tipsShownThisSession() || tipsHidden(userId)) return;
    markTipsShown();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- browser-only state, read once after mount
    setTips(shuffled(TIPS));
  }, [userId]);

  const open = tips !== null;
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setTips(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!tips || !userId) return null;
  const close = () => setTips(null);
  const step = (by: number) => setIndex((i) => (i + by + tips.length) % tips.length);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-[2px]" onClick={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tips-title"
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-border-strong bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
          <h2 id="tips-title" className="m-0 font-heading text-xl font-medium">
            <span aria-hidden="true" className="mr-2 text-accent">
              ✦
            </span>
            Useful tips{" "}
            <span className="font-sans text-sm font-normal text-muted-foreground">
              {index + 1}/{tips.length}
            </span>
          </h2>
          <button ref={closeRef} type="button" aria-label="Close tips" onClick={close} className={`${ROUND} text-lg`}>
            ×
          </button>
        </div>
        <div className="flex items-center gap-3 px-5 py-6">
          <button type="button" aria-label="Previous tip" onClick={() => step(-1)} className={`${ROUND} text-xl`}>
            ‹
          </button>
          <p aria-live="polite" className="m-0 flex min-h-[3.4em] flex-1 items-center justify-center text-center text-base leading-relaxed text-foreground">
            {tips[index]}
          </p>
          <button type="button" aria-label="Next tip" onClick={() => step(1)} className={`${ROUND} text-xl`}>
            ›
          </button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-raised px-5 py-3">
          <label className="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm text-prose-muted">
            <input
              type="checkbox"
              checked={dontShow}
              onChange={(e) => {
                setDontShow(e.target.checked);
                setTipsHidden(userId, e.target.checked);
              }}
              className="size-4 accent-[var(--color-accent)]"
            />
            Don&apos;t show this again
          </label>
          <button
            type="button"
            onClick={close}
            className="min-h-10 rounded-lg bg-accent px-5 text-sm font-semibold text-accent-foreground hover:brightness-110"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
