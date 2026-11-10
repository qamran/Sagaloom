"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { FeatureCardData } from "@/lib/types";

const BADGE: Record<FeatureCardData["status"], { label: string; cls: string; summary: string }> = {
  live: { label: "Live", cls: "bg-place text-background", summary: "bg-live-summary text-place" },
  configured: { label: "Configured", cls: "bg-event text-background", summary: "bg-configured-summary text-event" },
  off: { label: "Off", cls: "bg-border-strong text-foreground", summary: "bg-off-summary text-muted-foreground" },
};

const CARD: Record<FeatureCardData["status"], string> = {
  live: "border border-border bg-panel-2",
  configured: "border border-configured-border bg-panel-2",
  off: "border border-dashed border-border-strong bg-panel",
};

function TryLink({ href }: { href: string }) {
  const label = href.startsWith("/") ? "Try it →" : "Jump there →";
  return href.startsWith("/") ? (
    <Link href={href}>{label}</Link>
  ) : (
    <a href={href}>{label}</a>
  );
}

/** The feature map (R20.5): one card per brief requirement and bonus task, with its live status. */
export function FeatureMap({ features, highlight }: { features: FeatureCardData[]; highlight?: string }) {
  const lit = useRef<HTMLElement | null>(null);
  useEffect(() => {
    lit.current?.scrollIntoView?.({ block: "center" });
  }, [highlight, features.length]);
  const count = (s: FeatureCardData["status"]) => features.filter((f) => f.status === s).length;
  return (
    <section aria-label="Feature map" className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="m-0 font-heading text-[30px] font-medium">Feature map</h1>
        <span className="text-[13px] text-muted-foreground">
          What the brief asks for, and what this build shows right now
        </span>
        <span className="ml-auto flex gap-2 text-xs">
          {(["live", "configured", "off"] as const).map((s) => (
            <span key={s} className={`rounded-full px-2.5 py-0.5 ${BADGE[s].summary}`}>
              {count(s)} {BADGE[s].label}
            </span>
          ))}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {features.map((f) => (
          <article
            key={f.id}
            ref={f.id === highlight ? lit : undefined}
            aria-label={f.title}
            data-highlighted={f.id === highlight ? "true" : undefined}
            className={`flex flex-col gap-1.5 rounded-xl px-4 py-3.5 ${CARD[f.status]} ${
              f.id === highlight ? "outline outline-2 outline-offset-2 outline-myth" : ""
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-px text-[11px] font-semibold ${BADGE[f.status].cls}`}>
                {BADGE[f.status].label}
              </span>
              <span className="text-[11px] text-muted-foreground">{f.brief_ref}</span>
            </div>
            <h2 className={`m-0 text-base font-semibold ${f.status === "off" ? "text-prose-muted" : ""}`}>
              {f.title}
            </h2>
            <p className={`m-0 text-[13px] ${f.status === "off" ? "text-muted-foreground" : "text-prose-muted"}`}>
              {f.detail}
            </p>
            <div className="mt-1 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{f.req_ids.join(", ")}</span>
              {f.try_href ? <TryLink href={f.try_href} /> : <span className="text-muted-foreground">Planned</span>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
