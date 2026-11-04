import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EntityChip } from "@/components/EntityChip";

describe("EntityChip", () => {
  it("renders link with type label and colour class", () => {
    render(<EntityChip type="place" name="Sky of Velmar" href="/canon/ent_0007" />);
    const link = screen.getByRole("link", { name: /Sky of Velmar/ });
    expect(link).toHaveAttribute("href", "/canon/ent_0007");
    expect(link.className).toContain("text-place");
    // colour is not the only signal: the type is in the accessible name
    expect(screen.getByText("place")).toHaveClass("sr-only");
    expect(link).toHaveAccessibleName("place Sky of Velmar");
  });

  it("is not a link without href", () => {
    render(<EntityChip type="character" name="Mira Vale" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Mira Vale").parentElement?.className).toContain("text-character");
  });
});
