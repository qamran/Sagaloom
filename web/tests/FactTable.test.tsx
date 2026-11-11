import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Cite, FactTable, SecretValue, type SecretOf } from "@/components/FactTable";
import type { FactRow } from "@/lib/factRows";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

describe("FactTable secret pieces and the world toggle", () => {
  it("SecretValue is masked until the toggle is on", () => {
    const { unmount } = render(<SecretValue value="Under the bell" secret />);
    expect(screen.queryByText("Under the bell")).toBeNull();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<SecretValue value="Under the bell" secret />);
    expect(screen.getByText("Under the bell")).toBeInTheDocument();
  });

  it("Cite shows the title when the toggle is on", () => {
    const { unmount } = render(<Cite id="ent_0019" title="The Choir Ledger" secret />);
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<Cite id="ent_0019" title="The Choir Ledger" secret />);
    expect(screen.getByText("The Choir Ledger")).toBeInTheDocument();
  });
});

describe("FactTable layout: stacked below sm, a table from sm up", () => {
  const f = (value: string) => ({ key: "Weather", value, refs: [], status: "canon" as const, told_by: null });
  const rows: FactRow[] = [{ key: "Weather", canon: [f("Evening sea fog")], proposed: [f("Evening sea fog")], result: "Matches", flags: [] }];
  const none = () => false;
  const secretOf: SecretOf = { entry: false, canon: none, proposed: none, existing: none, incoming: none, text: none, cite: none, ownEntry: none };
  const renderTable = () => render(<FactTable rows={rows} secretOf={secretOf} typeOf={() => undefined} />);

  it("is a block (stacked) layout that turns back into a table at sm", () => {
    renderTable();
    const table = screen.getByRole("table");
    expect(table).toHaveClass("block", "sm:table", "sm:table-fixed");
    expect(table.querySelector("thead")).toHaveClass("hidden", "sm:table-header-group");
    for (const el of table.querySelectorAll("tbody, tbody tr, tbody td")) expect(el.className).toMatch(/(^| )block( |$)/);
    for (const td of table.querySelectorAll("td")) expect(td.className).toMatch(/sm:table-cell/);
  });

  it("labels each stacked value, and the labels go away at sm", () => {
    renderTable();
    const cells = within(screen.getByRole("table")).getAllByRole("cell");
    expect(cells.map((c) => c.getAttribute("data-label"))).toEqual([null, "In canon", "Proposed", "Result"]);
    for (const c of cells.slice(1)) {
      expect(c.className).toContain("before:content-[attr(data-label)]");
      expect(c.className).toContain("sm:before:content-none");
    }
  });

  it("never breaks the fact name inside a word", () => {
    renderTable();
    const fact = within(screen.getByRole("table")).getAllByRole("cell")[0];
    expect(fact).toHaveTextContent("Weather");
    expect(fact).toHaveClass("break-normal");
    expect(fact.className).not.toMatch(/break-words|break-all/);
  });
});
