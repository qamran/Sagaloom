import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SecretsToggle } from "@/components/SecretsToggle";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

describe("SecretsToggle", () => {
  it("is a Show secrets button whose aria-pressed follows the state", async () => {
    render(<SecretsToggle />);
    const btn = screen.getByRole("button", { name: "Show secrets" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w1"))).toBe("true");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "false");
  });
});
