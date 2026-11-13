import type { Metadata } from "next";
import { CHECKED_ON, COMPETITORS, FEATURES, PRODUCTS, type Cell } from "@/lib/competitors";

export const metadata: Metadata = { title: "Compare · Sagaloom" };

const MARK: Record<Cell["mark"], { symbol: string; label: string; className: string }> = {
  yes: { symbol: "✓", label: "Yes", className: "text-accent" },
  partial: { symbol: "◐", label: "Partly", className: "text-myth" },
  no: { symbol: "—", label: "No", className: "text-muted-foreground" },
};

function CellView({ cell }: { cell: Cell }) {
  const m = MARK[cell.mark];
  return (
    <>
      <span aria-hidden="true" className={`mr-1.5 font-semibold ${m.className}`}>
        {m.symbol}
      </span>
      <span className="sr-only">{m.label}. </span>
      {cell.note && <span>{cell.note}</span>}
    </>
  );
}

/** Links to the competing products and a feature-by-feature comparison with Sagaloom. */
export default function ComparePage() {
  return (
    <main className="flex flex-col gap-6 px-4 py-6 md:px-11 md:py-[30px]">
      <header className="flex flex-col gap-2">
        <h1 className="m-0 font-heading text-[clamp(26px,4vw,34px)] font-medium leading-[1.15]">Compare</h1>
        <p className="m-0 max-w-3xl text-[15px] leading-relaxed text-prose-muted">
          Other tools that keep a fictional world&apos;s lore, and how their features line up with Sagaloom&apos;s.
        </p>
      </header>

      <section aria-labelledby="compare-products">
        <h2 id="compare-products" className="m-0 font-heading text-xl font-medium">
          The products
        </h2>
        <ul className="m-0 mt-3 grid list-none gap-3 p-0 sm:grid-cols-2 xl:grid-cols-4">
          {COMPETITORS.map((c) => (
            <li key={c.name} className="flex flex-col gap-1.5 rounded-xl border border-border bg-panel p-4">
              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-heading text-[17px] font-semibold"
              >
                {c.name}
                <span className="sr-only"> (opens in a new tab)</span>
                <span aria-hidden="true"> ↗</span>
              </a>
              <p className="m-0 text-sm text-foreground">{c.category}</p>
              <p className="m-0 text-[13px] text-muted-foreground">For: {c.audience}</p>
              <p className="m-0 text-[13px] text-prose-muted">{c.closeness}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="compare-features">
        <h2 id="compare-features" className="m-0 font-heading text-xl font-medium">
          Features
        </h2>
        <p className="m-0 mt-1 text-[13px] text-muted-foreground">
          ✓ yes · ◐ partly or on some plans · — no or not advertised. Highlighted rows are where Sagaloom differs most.
        </p>
        {/* Scrolls sideways on a phone; focusable so the keyboard can scroll it too. */}
        <div
          tabIndex={0}
          role="region"
          aria-label="Feature comparison table"
          className="mt-3 overflow-x-auto rounded-xl border border-border"
        >
          <table className="w-full min-w-[860px] border-collapse text-left text-[13px] leading-relaxed">
            <caption className="sr-only">Sagaloom&apos;s features compared with {COMPETITORS.map((c) => c.name).join(", ")}</caption>
            <thead className="bg-raised">
              <tr>
                <th scope="col" className="w-[19%] px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.9px] text-muted-foreground">
                  Feature
                </th>
                {PRODUCTS.map((name, i) => (
                  <th
                    key={name}
                    scope="col"
                    className={`px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.9px] ${
                      i === 0 ? "bg-panel-3 text-accent" : "text-muted-foreground"
                    }`}
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FEATURES.map((row) => (
                <tr key={row.feature} className={`border-t border-border align-top ${row.highlight ? "bg-panel" : ""}`}>
                  <th scope="row" className="px-4 py-3 font-heading text-[14px] font-semibold text-foreground">
                    {row.feature}
                  </th>
                  {row.cells.map((cell, i) => (
                    <td key={PRODUCTS[i]} className={`px-4 py-3 ${i === 0 ? "bg-panel-3 text-foreground" : "text-prose-muted"}`}>
                      <CellView cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="m-0 mt-3 max-w-3xl text-xs leading-relaxed text-muted-foreground">
          Competitor features are the vendors&apos; own claims from their public pages, checked {CHECKED_ON}. &ldquo;Not
          advertised&rdquo; means we found no mention of it; it does not mean the product lacks the feature.
        </p>
      </section>
    </main>
  );
}
