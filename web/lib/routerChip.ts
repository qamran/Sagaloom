import type { Mode } from "./types";

/** The router chip's text: `Router · {mode}`, plus `· Jev {n}%` for a Jev decision with a confidence (R6.6). */
export function routerChipLabel(mode: Mode, engine?: "llm" | "jev", confidence?: number | null): string {
  const base = `Router · ${mode}`;
  return engine === "jev" && typeof confidence === "number" ? `${base} · Jev ${Math.round(confidence * 100)}%` : base;
}
