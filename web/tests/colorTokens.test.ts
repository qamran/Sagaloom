import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// M13: every colour a class or a `var(--color-…)` names must be a token in app/globals.css, so a
// typo such as `bg-panle-2` (which Tailwind silently drops) fails here instead of in the browser.

const ROOT = join(__dirname, "..");
const DIRS = ["app", "components", "lib"];
const UTILITY = "bg|text|border|ring|fill|stroke|outline|divide|from|to";
// The name runs on through `[` and `$` so an arbitrary value or a template piece can be skipped.
const CLASS = new RegExp(String.raw`(?<![\w\-\[])(?:${UTILITY})-([\w\-./\[$]+)`, "g");
const VAR = /var\(--color-([\w-]+)\)/g;

const PALETTE = /^(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}$/;
const KEYWORD = /^(white|black|transparent|current|inherit)$/;
// Utilities sharing a prefix that are not colours: text sizes and alignment, border sides and
// styles, ring and outline widths, gradient directions, background sizing.
const NOT_COLOUR = new RegExp(
  "^(" +
    [
      String.raw`xs|sm|base|lg|\d?xl|left|center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip`,
      String.raw`[tblrxyse]|[tblrxyse]-\d+|none|solid|dashed|dotted|double|hidden|collapse|separate`,
      String.raw`inset|offset|width|offset-\d+|cover|contain|auto|fixed|local|scroll|no-repeat|repeat|origin-\w+`,
      String.raw`gradient-to-\w+|linear-to-\w+|\w+-gradient`,
    ].join("|") +
    ")$",
);

/** The colour names in `source` that `defined` does not hold, in order of first use. */
export function undefinedTokens(source: string, defined: Set<string>): string[] {
  const names = [
    ...[...source.matchAll(CLASS)].map((m) => m[1]),
    ...[...source.matchAll(VAR)].map((m) => m[1]),
  ];
  const out: string[] = [];
  for (const raw of names) {
    if (raw.includes("[") || raw.includes("$")) continue; // arbitrary value or template piece
    const name = raw.replace(/\/[\w.[\]]+$/, ""); // opacity suffix
    if (!name || /^[\d.]+$/.test(name) || PALETTE.test(name) || KEYWORD.test(name) || NOT_COLOUR.test(name)) continue;
    if (!defined.has(name) && !out.includes(name)) out.push(name);
  }
  return out;
}

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

  it("bites on an undefined token", () => {
    expect(undefinedTokens('className="bg-nope text-foreground"', DEFINED)).toEqual(["nope"]);
    expect(undefinedTokens("color: var(--color-nope-2);", DEFINED)).toEqual(["nope-2"]);
    // The scan sees real names: with nothing defined, the card's tokens all come back.
    const card = readFileSync(join(ROOT, "components", "ApprovalCard.tsx"), "utf8");
    expect(undefinedTokens(card, new Set())).toEqual(expect.arrayContaining(["accent", "panel-2", "conflict-line", "muted-foreground"]));
    expect(undefinedTokens('className="bg-panel-2/60 text-sm border-b ring-2 bg-red-500 text-[13px]"', DEFINED)).toEqual([]);
  });
});
