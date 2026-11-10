// The colour-token scanner behind colorTokens.test.ts (M13): which class names and
// `var(--color-…)` uses in a source string name a colour that globals.css does not define.

const UTILITY = "bg|text|border|ring|fill|stroke|outline|divide|from|to";
// The name runs on through `[` and `$` so an arbitrary value or a template piece can be skipped.
const CLASS = new RegExp(String.raw`(?<![\w\-\[])(${UTILITY})-([\w\-./\[$]+)`, "g");
const SIDE = /^[tblrxyse]-(?=[a-z])/;
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
    // `border-t-accent` names the colour `accent`; the side only picks the edge.
    ...[...source.matchAll(CLASS)].map((m) => (m[1] === "border" ? m[2].replace(SIDE, "") : m[2])),
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

/** The arbitrary hex colours (`bg-[#1f2725]`, `border-[#abc]`) in `source`, in order. */
export function arbitraryHexColours(source: string): string[] {
  return [...source.matchAll(new RegExp(String.raw`(?<![\w\-\[])(?:${UTILITY})-\[#[0-9a-fA-F]{3,8}\]`, "g"))].map((m) => m[0]);
}
