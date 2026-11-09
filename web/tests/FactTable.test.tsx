import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Cite, SecretValue } from "@/components/FactTable";
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
