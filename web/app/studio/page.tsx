"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FeatureMap } from "@/components/FeatureMap";
import { GuardrailsPanel } from "@/components/GuardrailsPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { ProvidersPanel } from "@/components/ProvidersPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ToolsPanel } from "@/components/ToolsPanel";
import { UsagePanel } from "@/components/UsagePanel";
import { getModels, getSettings, getStudio } from "@/lib/api";

const SECTIONS = [
  ["feature-map", "Feature map"],
  ["agent-graph", "Agent graph"],
  ["models", "Models and providers"],
  ["tools", "Tools"],
  ["memory", "Memory"],
  ["guardrails", "Guardrails"],
  ["settings", "Settings"],
  ["usage", "Usage"],
];

/** The Developer page (R20.4): kept apart from the author's screens. */
function Studio() {
  const highlight = useSearchParams().get("card") ?? undefined;
  const studio = useQuery({ queryKey: ["studio"], queryFn: getStudio });
  const models = useQuery({ queryKey: ["settings", "models"], queryFn: getModels });
  const dev = useQuery({ queryKey: ["settings"], queryFn: getSettings });

  return (
    <div className="flex flex-1 flex-wrap">
      <nav
        aria-label="Studio sections"
        className="flex flex-[1_1_200px] flex-col gap-0.5 border-border bg-panel p-3 text-[13px] md:max-w-[220px] md:border-r md:px-3 md:py-5"
      >
        <div className="px-2 pb-3 font-heading text-[22px] font-semibold">Studio</div>
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-md px-2 py-[7px] text-foreground no-underline hover:bg-panel-3 hover:text-foreground">
            {label}
          </a>
        ))}
        <div className="mt-4 border-t border-border px-2 pt-2.5 text-xs text-muted-foreground">
          Settings here are kept apart from the author&apos;s screens.
        </div>
      </nav>
      <main className="flex min-w-0 flex-[999_1_640px] flex-col gap-7 px-4 py-6 md:px-9 md:py-7">
        {studio.isLoading && <p className="m-0 text-muted-foreground">Loading Studio…</p>}
        {studio.isError && (
          <p role="alert" className="m-0 text-conflict">
            Could not load Studio. Is the Sagaloom API running?
          </p>
        )}
        {studio.data && (
          <>
            <div id="feature-map" className="scroll-mt-4">
              <FeatureMap features={studio.data.features} highlight={highlight} />
            </div>
            <section
              id="agent-graph"
              aria-label="Agent graph"
              className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
            >
              <h2 className="m-0 font-heading text-[22px] font-medium">Agent graph</h2>
              <p className="m-0 text-xs text-muted-foreground">
                The compiled LangGraph, as Mermaid from <code className="font-mono">draw_mermaid()</code>. The
                rendered graph with the last run highlighted comes in M2.
              </p>
              <pre className="m-0 max-h-[360px] overflow-auto rounded-lg border border-border bg-[#101314] p-3 font-mono text-xs leading-[1.55] text-[#c9c6bd]">
                {studio.data.mermaid || "The graph is not available."}
              </pre>
            </section>
            <div>
              {models.data ? (
                <ProvidersPanel providers={studio.data.providers} models={models.data} />
              ) : (
                <p className="m-0 text-muted-foreground">
                  {models.isError ? "Could not load the model list." : "Loading models…"}
                </p>
              )}
            </div>
            <ToolsPanel />
            <MemoryPanel />
            {dev.data ? (
              <>
                <GuardrailsPanel payload={dev.data} />
                <SettingsPanel payload={dev.data} />
              </>
            ) : (
              <p id="guardrails" className="m-0 text-muted-foreground">
                {dev.isError ? "Could not load the guardrails and settings." : "Loading settings…"}
              </p>
            )}
            <UsagePanel usage={studio.data.usage} />
          </>
        )}
      </main>
    </div>
  );
}

export default function StudioPage() {
  return (
    <Suspense fallback={<p className="m-0 p-6 text-muted-foreground">Loading Studio…</p>}>
      <Studio />
    </Suspense>
  );
}
