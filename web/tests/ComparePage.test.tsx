import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ComparePage from "@/app/compare/page";
import { COMPETITORS, FEATURES, PRODUCTS } from "@/lib/competitors";

describe("ComparePage", () => {
  it("links to every competitor in a new tab", () => {
    render(<ComparePage />);
    const list = within(screen.getByRole("region", { name: "The products" }));
    for (const [name, url] of [
      ["Realmweaver", "https://realmweaver.io"],
      ["LitMemo", "https://litmemo.com"],
      ["StoryGuard", "https://www.storyguard.app"],
      ["LoreKeeper", "https://lorekeeper.com"],
    ]) {
      const link = list.getByRole("link", { name: new RegExp(`^${name}`) });
      expect(link).toHaveAttribute("href", url);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("compares Sagaloom with each competitor, one column per product", () => {
    render(<ComparePage />);
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Feature", "Sagaloom", "Realmweaver", "LitMemo", "StoryGuard", "LoreKeeper"]);
    const row = within(table).getByRole("row", { name: /Check runs automatically when you add a fact/ });
    expect(within(row).getAllByRole("cell")[0]).toHaveTextContent("Yes. Every proposed write");
  });

  it("has a cell for every product in every row, and states when the claims were checked", () => {
    for (const row of FEATURES) expect(row.cells, row.feature).toHaveLength(PRODUCTS.length);
    expect(PRODUCTS).toHaveLength(COMPETITORS.length + 1);
    render(<ComparePage />);
    expect(screen.getByText(/vendors' own claims from their public pages, checked 2026-11-04/)).toBeInTheDocument();
  });
});
