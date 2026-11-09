"use client";

import { useShowSecrets } from "@/lib/secrets";
import { useWorld } from "@/lib/world";

/** The world-level master switch for secrets (this tab only); per-item Show buttons stay. */
export function SecretsToggle() {
  const { world } = useWorld();
  const [on, setOn] = useShowSecrets(world?.id);
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => setOn(!on)}
      className={`min-h-11 rounded-lg border px-3 text-[13px] sm:min-h-9 ${
        on ? "border-conflict text-conflict" : "border-border-strong text-muted-foreground"
      }`}
    >
      Show secrets
    </button>
  );
}
