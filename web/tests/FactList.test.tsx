import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FactList } from "@/components/FactList";
import type { Fact } from "@/lib/types";

const facts: Fact[] = [
  { key: "Moons", value: "One", refs: [], status: "canon", told_by: null },
  { key: "Moons", value: "Three", refs: [], status: "myth", told_by: "the Ashen Choir" },
  { key: "Mayor", value: "Secretly a Choir member", refs: [], status: "secret", told_by: null },
];

describe("FactList", () => {
  it("shows myth badge and told-by, hides secret until Show is clicked", async () => {
    render(<FactList facts={facts} />);
    expect(screen.getByText("myth")).toBeInTheDocument();
    expect(screen.getByText("told by the Ashen Choir")).toBeInTheDocument();
    expect(screen.getByText("Three")).toBeInTheDocument();

    expect(screen.queryByText("Secretly a Choir member")).toBeNull();
    expect(screen.getByText("secret")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(screen.getByText("Secretly a Choir member")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<FactList facts={[]} />);
    expect(screen.getByText(/no facts/i)).toBeInTheDocument();
  });
});

describe("FactList reveal state", () => {
  it("does not carry a reveal over to a different fact at the same position", async () => {
    const first: Fact[] = [
      { key: "Mayor", value: "Secretly a Choir member", refs: [], status: "secret", told_by: null },
    ];
    const second: Fact[] = [
      { key: "Vault", value: "Under the bell tower", refs: [], status: "secret", told_by: null },
    ];
    const { rerender } = render(<FactList facts={first} />);
    await userEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(screen.getByText("Secretly a Choir member")).toBeInTheDocument();
    rerender(<FactList facts={second} />);
    expect(screen.queryByText("Under the bell tower")).toBeNull();
    expect(screen.getByRole("button", { name: /show/i })).toBeInTheDocument();
  });

  it("uses screen-reader text for the hidden placeholder", () => {
    render(<FactList facts={facts} />);
    expect(screen.getByText("hidden secret")).toHaveClass("sr-only");
  });
});
