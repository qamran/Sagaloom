import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { clerkAppearance } from "@/lib/clerkAppearance";

// The Clerk colours are literal copies of globals.css tokens: this keeps them in step.
describe("Clerk appearance", () => {
  it("uses the app's colour tokens", () => {
    const css = readFileSync(path.join(__dirname, "../app/globals.css"), "utf8");
    const token = (name: string) => css.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`, "i"))?.[1];
    const v = clerkAppearance.variables;
    expect(v.colorPrimary).toBe(token("accent"));
    expect(v.colorPrimaryForeground).toBe(token("accent-foreground"));
    expect(v.colorBackground).toBe(token("panel"));
    expect(v.colorForeground).toBe(token("foreground"));
    expect(v.colorMutedForeground).toBe(token("muted-foreground"));
    expect(v.colorInput).toBe(token("panel-3"));
    expect(v.colorDanger).toBe(token("failed"));
  });
});
