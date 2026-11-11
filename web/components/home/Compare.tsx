import { EYEBROW, H2, LEDE, WRAP } from "@/components/home/styles";

// The README's caveat, verbatim.
const CAVEAT =
  "\"Not advertised\" means we found no mention of it on the vendor's public pages (checked 2026-11-04); it is not independently verified, and it does not mean the product lacks the feature. These are the vendors' own claims.";
const VENDORS = ["Sagaloom", "Realmweaver", "LitMemo", "StoryGuard"] as const;

// The first three rows of the README's "How Sagaloom compares" table (checked 2026-11-04). The other
// vendors' cells are word for word; Sagaloom's are the same claims without developer terms.
const ROWS: { label: string; cells: string[] }[] = [
  {
    label: "Fact-level contradiction check",
    cells: [
      "Every proposed write is checked automatically, fact against fact (keyed facts first, then prose), and each flag cites entry IDs and quotes both sides",
      "On demand, flags by severity and suggests fixes; automatic check, fact-level check and entry IDs not advertised",
      "Whole manuscript, cites chapter and paragraph; no check on adding a setting entry advertised",
      "On request; automatic only on the $18 plan",
    ],
  },
  {
    label: "Human approval before any write",
    cells: [
      "Always: nothing is written until you approve, edit, reject or save it as a myth",
      "Described for imports only",
      "Yes: new cards and AI paragraphs are confirmed",
      "Yes: every codex update",
    ],
  },
  {
    label: "Import with verbatim text",
    cells: [
      "Yes: the model only points at passages, and the server stores your own words",
      "Keeps the original text without rewriting it",
      "Extracts cards from pasted text; verbatim storage not advertised",
      "Pasted notes; verbatim storage not advertised",
    ],
  },
];

/** A short version of the README comparison, with its caveat and checked date (M5 §5.7 item 5). */
export function Compare() {
  return (
    <section aria-labelledby="home-compare" className="border-t border-border py-16 sm:py-20">
      <div className={WRAP}>
        <p className={EYEBROW}>Compare</p>
        <h2 id="home-compare" className={H2}>
          How it compares
        </h2>
        <p className={LEDE}>
          Sagaloom is closest to Realmweaver (a world-building coach with a wiki and a consistency checker). LitMemo (a
          story bible and manuscript editor, Traditional Chinese only) and StoryGuard (a campaign notebook for game masters) overlap on parts of it.
        </p>
        {/* Scrolls sideways on a phone; focusable so the keyboard can scroll it too. */}
        <div tabIndex={0} role="region" aria-label="Comparison table" className="mt-8 overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[720px] border-collapse text-left text-[13px] leading-relaxed">
            <caption className="sr-only">How Sagaloom compares with Realmweaver, LitMemo and StoryGuard</caption>
            <thead className="bg-raised">
              <tr>
                <th scope="col" className="w-[18%] px-4 py-3">
                  <span className="sr-only">Feature</span>
                </th>
                {VENDORS.map((v) => (
                  <th
                    key={v}
                    scope="col"
                    className={`px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.9px] ${
                      v === "Sagaloom" ? "bg-panel-3 text-accent" : "text-muted-foreground"
                    }`}
                  >
                    {v}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.label} className="border-t border-border align-top">
                  <th scope="row" className="px-4 py-3.5 font-heading text-[15px] font-semibold text-foreground">
                    {r.label}
                  </th>
                  {r.cells.map((c, i) => (
                    <td key={i} className={`px-4 py-3.5 ${i === 0 ? "bg-panel-3 text-foreground" : "text-prose-muted"}`}>
                      {c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="m-0 mt-4 max-w-3xl text-xs leading-relaxed text-muted-foreground">{CAVEAT}</p>
      </div>
    </section>
  );
}
