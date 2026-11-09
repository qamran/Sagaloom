"use client";

import { ExportButton } from "@/components/ExportButton";
import { GetStarted } from "@/components/GetStarted";
import { useWorld } from "@/lib/world";

export default function CanonHome() {
  const { world, isLoading, error, startWorld } = useWorld();

  if (isLoading) return <p className="text-muted-foreground">Loading worlds…</p>;
  if (error || !world) {
    return (
      <p role="alert" className="text-conflict">
        Could not reach the Sagaloom API. Is it running?
      </p>
    );
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="text-xs uppercase tracking-[1px] text-accent">Canon</div>
        <h1 className="m-0 font-heading text-[clamp(30px,5vw,42px)] font-medium leading-[1.1]">
          {world.name}
        </h1>
        <p className="m-0 font-heading text-[19px] text-prose-muted">
          Choose an entry from the list to read it and its facts.
        </p>
      </div>
      <ExportButton worldId={world.id} />
      <GetStarted world={world} onStartOwn={() => void startWorld("My World")} />
    </div>
  );
}
