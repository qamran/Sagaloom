import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { arbitraryHexColours, undefinedTokens } from "./colorTokenScan";

// M13: every colour a class or a `var(--color-…)` names must be a token in app/globals.css, so a
// typo such as `bg-panle-2` (which Tailwind silently drops) fails here instead of in the browser.

const ROOT = join(__dirname, "..");
const DIRS = ["app", "components", "lib"];
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return walk(p);
    return /\.(tsx?|css)$/.test(f) ? [p] : [];
  });
}

const css = readFileSync(join(ROOT, "app", "globals.css"), "utf8");
const DEFINED = new Set([...css.matchAll(/--color-([\w-]+)\s*:/g)].map((m) => m[1]));

describe("colour tokens (M13)", () => {
  it("every colour used under app, components and lib is defined in globals.css", () => {
    const missing = DIRS.flatMap((d) => walk(join(ROOT, d))).flatMap((file) =>
      undefinedTokens(readFileSync(file, "utf8"), DEFINED).map((n) => `${relative(ROOT, file)}: ${n}`),
    );
    expect(missing).toEqual([]);
  });

  it("no arbitrary hex colour in class strings", () => {
    const sites = DIRS.flatMap((d) => walk(join(ROOT, d))).flatMap((file) =>
      arbitraryHexColours(readFileSync(file, "utf8")).map((c) => `${relative(ROOT, file)}: ${c}`),
    );
    expect(sites).toEqual([]);
  });

  it("side-colour utilities resolve", () => {
    expect(undefinedTokens('className="border-t-accent border-x-conflict-line border-b-2"', DEFINED)).toEqual([]);
    expect(undefinedTokens('className="border-t-nope"', DEFINED)).toEqual(["nope"]);
    expect(arbitraryHexColours('className="bg-[#1f2725] border-[#abc] w-[80%] text-[13px]"')).toEqual(["bg-[#1f2725]", "border-[#abc]"]);
    expect(arbitraryHexColours('className="border-t-[#abc]"')).toEqual(["border-t-[#abc]"]);
    expect(arbitraryHexColours('className="divide-x-[#123456] border-t-[2px] w-x-[#abc]"')).toEqual(["divide-x-[#123456]"]);
  });

  it("bites on an undefined token", () => {
    expect(undefinedTokens('className="bg-nope text-foreground"', DEFINED)).toEqual(["nope"]);
    expect(undefinedTokens("color: var(--color-nope-2);", DEFINED)).toEqual(["nope-2"]);
    // The scan sees real names: with nothing defined, the card's tokens all come back.
    const card = readFileSync(join(ROOT, "components", "ApprovalCard.tsx"), "utf8");
    expect(undefinedTokens(card, new Set())).toEqual(expect.arrayContaining(["accent", "panel-2", "conflict-line", "muted-foreground"]));
    expect(undefinedTokens('className="bg-panel-2/60 text-sm border-b ring-2 bg-red-500 text-[13px]"', DEFINED)).toEqual([]);
  });
});
