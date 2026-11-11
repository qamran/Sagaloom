import type { RoleUsage } from "@/lib/types";

export type StepKey = "guard" | "router" | "chat" | "check" | "extraction" | "other";

/** The pipeline steps a model call can belong to, in display order (M4, R14.3). `bar` is the step's colour in a cost bar. */
export const STEPS: readonly { key: StepKey; name: string; bar: string }[] = [
  { key: "guard", name: "Guard", bar: "bg-rule" },
  { key: "router", name: "Router", bar: "bg-place" },
  { key: "chat", name: "Chat", bar: "bg-accent" },
  { key: "check", name: "Check", bar: "bg-event" },
  { key: "extraction", name: "Extraction", bar: "bg-faction" },
  { key: "other", name: "Other", bar: "bg-muted-foreground" },
];

/** The roles whose messages the chat shows (the ones that carry a turn_id). */
export const SHOWN_ROLES: readonly string[] = ["user", "assistant", "review", "guard", "memory"];

const STEP_OF_ROLE: Record<string, StepKey> = {
  guard: "guard",
  router: "router",
  agent: "chat",
  judge: "check",
  extractor: "extraction",
};

/** The step a PromptLog role belongs to; anything unknown or missing is "other". */
export function stepOf(role: string | null | undefined): StepKey {
  return (role && STEP_OF_ROLE[role]) || "other";
}

export interface StepTotal {
  key: StepKey;
  name: string;
  bar: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

/** Roll per-role usage up to steps: merged, empty steps dropped, in STEPS order. */
export function stepsFromRoles(byRole: RoleUsage[]): StepTotal[] {
  return STEPS.map((step) => {
    const total: StepTotal = { ...step, calls: 0, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 };
    for (const r of byRole) {
      if (stepOf(r.role) !== step.key) continue;
      total.calls += r.calls;
      total.prompt_tokens += r.prompt_tokens;
      total.completion_tokens += r.completion_tokens;
      total.cost_usd += r.cost_usd;
    }
    return total;
  }).filter((t) => t.calls > 0);
}
