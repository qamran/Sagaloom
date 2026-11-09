import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FactList } from "@/components/FactList";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { Named } from "@/lib/mentions";
import type { Fact } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

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

describe("FactList hideAll and the world toggle", () => {
  it("hideAll hides canon-status facts too, under a generic key", () => {
    render(<FactList facts={facts} hideAll />);
    expect(screen.queryByText("One")).toBeNull();
    expect(screen.queryByText("Moons")).toBeNull();
    expect(screen.getAllByText("Secret fact")).toHaveLength(3);
  });

  it("the toggle reveals everything, hideAll facts included", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<FactList facts={facts} hideAll />);
    expect(screen.getByText("One")).toBeInTheDocument();
    expect(screen.getByText("Secretly a Choir member")).toBeInTheDocument();
  });

  it("per-item Show still works with the toggle off", async () => {
    render(<FactList facts={facts} hideAll />);
    await userEvent.click(screen.getAllByRole("button", { name: /show secret fact/i })[0]);
    expect(screen.getByText("One")).toBeInTheDocument();
  });

  it("without hideAll, only secret facts are hidden", () => {
    render(<FactList facts={facts} />);
    expect(screen.getByText("One")).toBeInTheDocument();
  });
});

describe("FactList entity chips", () => {
  const entries: Named[] = [
    { id: "ent_0001", title: "Velmar", type: "place", aliases: [], status: "canon" },
    { id: "ent_0004", title: "Ashen Choir", type: "faction", aliases: [], status: "canon" },
    { id: "ent_0019", title: "The Choir Ledger", type: "item", aliases: [], status: "secret" },
  ];
  const list = (f: Partial<Fact>): Fact[] => [
    { key: "Moons", value: "Three", refs: [], status: "canon", told_by: null, ...f },
  ];

  it("renders told_by naming an entry as a chip, and refs as chips", () => {
    render(<FactList entries={entries} facts={list({ told_by: "the Ashen Choir", refs: ["ent_0001"] })} />);
    expect(screen.getByRole("link", { name: /Ashen Choir/ })).toHaveAttribute("href", "/canon/ent_0004");
    expect(screen.getByRole("link", { name: /Velmar/ })).toHaveAttribute("href", "/canon/ent_0001");
  });

  it("never turns a hidden secret ref or teller into a chip or shows its title", () => {
    render(<FactList entries={entries} facts={list({ told_by: "The Choir Ledger", refs: ["ent_0019"] })} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getAllByText(/Choir Ledger/)).toHaveLength(1); // the plain told-by text only
  });

  it("chips the secret entry once the world toggle is on", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<FactList entries={entries} facts={list({ refs: ["ent_0019"] })} />);
    expect(screen.getByRole("link", { name: /The Choir Ledger/ })).toHaveAttribute("href", "/canon/ent_0019");
    sessionStorage.clear();
  });
});
