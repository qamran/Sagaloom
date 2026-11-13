// The Compare page's data. Every competitor claim comes from the vendors' public pages, checked
// 2026-11-04 (internal docs/competitor_analysis/combined_analysis.md); Sagaloom's column is what this app does.

export const CHECKED_ON = "2026-11-04";

export type Competitor = {
  name: string;
  url: string;
  /** What kind of product it is, in a few words. */
  category: string;
  /** Who it is for. */
  audience: string;
  /** How close it is to Sagaloom. */
  closeness: string;
};

export const COMPETITORS: Competitor[] = [
  {
    name: "Realmweaver",
    url: "https://realmweaver.io",
    category: "AI world-building coach and wiki",
    audience: "Novelists, game masters, screenwriters, game developers",
    closeness: "Closest to Sagaloom: a canon wiki with an on-demand consistency checker",
  },
  {
    name: "LitMemo",
    url: "https://litmemo.com",
    category: "Story bible and manuscript tool",
    audience: "Serial novelists and manga creators (Traditional Chinese only)",
    closeness: "Overlaps on story-bible cards and a whole-manuscript check",
  },
  {
    name: "StoryGuard",
    url: "https://www.storyguard.app",
    category: "Campaign notebook and session tracker",
    audience: "Tabletop game masters",
    closeness: "Overlaps on approving every codex change and keeping secrets",
  },
  {
    name: "LoreKeeper",
    url: "https://lorekeeper.com",
    category: "Game-prep and generative media toolkit",
    audience: "Tabletop game masters",
    closeness: "A different category: it generates media from your lore; no contradiction check advertised",
  },
];

/** yes = has it, partial = limited or on some plans only, no = not offered or not advertised. */
export type Mark = "yes" | "partial" | "no";
export type Cell = { mark: Mark; note?: string };

/** Column order: Sagaloom, then COMPETITORS in order. */
export const PRODUCTS = ["Sagaloom", ...COMPETITORS.map((c) => c.name)];

const y = (note?: string): Cell => ({ mark: "yes", note });
const p = (note?: string): Cell => ({ mark: "partial", note });
const n = (note?: string): Cell => ({ mark: "no", note });

export type FeatureRow = { feature: string; cells: Cell[]; highlight?: boolean };

// Cells per row: Sagaloom, Realmweaver, LitMemo, StoryGuard, LoreKeeper.
export const FEATURES: FeatureRow[] = [
  {
    feature: "Contradiction check",
    highlight: true,
    cells: [
      y("Fact against fact, cites entry IDs and quotes both sides"),
      y("On demand, by severity, suggests fixes"),
      y("Whole manuscript, cites chapter and paragraph"),
      p("Manual; automatic on the $18 plan"),
      n("Not advertised"),
    ],
  },
  {
    feature: "Check runs automatically when you add a fact",
    highlight: true,
    cells: [y("Every proposed write"), n("On demand"), n("Not described"), p("Top plan only"), n()],
  },
  {
    feature: "Approval before the AI writes to canon",
    highlight: true,
    cells: [
      y("Every write: approve, edit, reject or save as myth"),
      p("Imports only"),
      y("Cards and AI paragraphs are confirmed"),
      y("Every codex update"),
      n("Not described"),
    ],
  },
  {
    feature: "Myths and rumours that raise no false alarms",
    highlight: true,
    cells: [y("Save as myth, optionally told by someone"), n(), n(), n(), n()],
  },
  {
    feature: "Real-world reference lookup",
    highlight: true,
    cells: [y("Wikipedia, marked as untrusted"), n(), n(), n(), n()],
  },
  {
    feature: "Hidden canon (secrets)",
    cells: [y("Masked on screen until Show secrets"), n(), n(), y("Kept out of recaps"), n()],
  },
  {
    feature: "Import existing material",
    cells: [
      y("Paste, .md/.txt files, fan-wiki pages; your words stored verbatim"),
      y(".docx, .pdf, .txt, .md, Google Docs"),
      y("Paste or bulk files"),
      y("Paste session notes"),
      y("PDF, docs, audio/video, Google Docs"),
    ],
  },
  {
    feature: "AI pulls out entities",
    cells: [y("Every candidate checked and approved"), y(), y("Cards"), y("After each session"), y()],
  },
  {
    feature: "Linked wiki or codex",
    cells: [y("Canon entries with links"), y("Living wiki"), y("Cards"), y("Codex"), y()],
  },
  {
    feature: "Export",
    cells: [
      y("Markdown zip, Obsidian-ready"),
      y("PDF, Word, Markdown, Fountain, FDX"),
      p("Markdown (paid)"),
      p("Campaign export (paid)"),
      y("PDF worldbook"),
    ],
  },
  {
    feature: "Relationship graph",
    cells: [n(), y("Typed relationships, family trees"), y(), n(), n()],
  },
  { feature: "Timeline", cells: [n("On the backlog"), y("Story Spine"), y("Plus foreshadowing"), y("Events"), n()] },
  { feature: "Maps", cells: [n(), y("Nested"), n(), y("Map view"), y()] },
  { feature: "Coaching the author", cells: [n("On the backlog"), y("Core feature"), n(), n(), n()] },
  {
    feature: "Writing or manuscript editor",
    cells: [n("A continuity editor, not a ghostwriter"), y("Manuscript workspace"), y("Plus serial publishing"), n(), y("Sourcebook editor")],
  },
  {
    feature: "Generative media",
    cells: [n(), n(), y("Manga panels"), n(), y("Images, video, sound effects, 3D")],
  },
  {
    feature: "Game-session tools",
    cells: [n(), p("Chronicle notes"), n(), y("Prep, notes, recaps"), y("Player Mode")],
  },
  {
    feature: "Choose the AI model",
    cells: [y("One model per role, from an allowlist"), n(), n(), p("Bring your own Anthropic key"), n()],
  },
  { feature: "Language", cells: [y("English"), y("English"), p("Traditional Chinese only"), y("English"), y("English")] },
];
