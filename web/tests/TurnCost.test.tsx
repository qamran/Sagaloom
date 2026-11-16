import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { TurnCost } from "@/components/TurnCost";
import { stepsFromRoles } from "@/lib/steps";
import type { RoleUsage, TurnUsage } from "@/lib/types";

const role = (r: string, prompt_tokens: number, completion_tokens: number, cost_usd: number): RoleUsage => ({
  role: r, calls: 1, prompt_tokens, completion_tokens, cost_usd,
});

/** The mockup's turn: guard, router, two agent calls and the judge. */
const turn: TurnUsage = {
  turn_id: "run_1",
  usage: { prompt_tokens: 8734, completion_tokens: 477, cost_usd: 0.0063 },
  by_role: [
    role("guard", 612, 18, 0.00041),
    role("router", 488, 12, 0.00032),
    { ...role("agent", 1904 + 2310, 96 + 141, 0.00121 + 0.00156), calls: 2 },
    role("judge", 3420, 210, 0.0028),
  ],
};

const LINE = "9,211 tokens · $0.0063 · 4 steps";

describe("TurnCost", () => {
  it("collapsed line shows tokens cost and step count", () => {
    render(<TurnCost turn={turn} />);
    const button = screen.getByRole("button", { name: LINE });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("expands to rows in pipeline order", async () => {
    render(<TurnCost turn={turn} />);
    const button = screen.getByRole("button", { name: LINE });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const table = screen.getByRole("table", { name: "Cost by step" });
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "Guard", "Router", "Chat", "Check", "Total",
    ]);
    const chat = within(table).getAllByRole("row").find((r) => r.textContent?.startsWith("Chat"))!;
    expect(chat).toHaveTextContent("2 calls");
    expect(chat).toHaveTextContent("4,214 → 237");
    expect(chat).toHaveTextContent("$0.0028");
    const total = within(table).getAllByRole("row").at(-1)!;
    expect(total).toHaveTextContent("8,734 → 477");
    expect(total).toHaveTextContent("$0.0063");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("row sums equal the total", async () => {
    render(<TurnCost turn={turn} />);
    await userEvent.click(screen.getByRole("button", { name: LINE }));
    const steps = stepsFromRoles(turn.by_role);
    // One row per step, plus the Total row.
    expect(within(screen.getByRole("table")).getAllByRole("rowheader")).toHaveLength(steps.length + 1);
    const sum = steps.reduce((a, s) => a + s.cost_usd, 0);
    expect(Math.abs(sum - turn.usage.cost_usd)).toBeLessThan(1e-9);
  });

  it("says 1 step and 1 call for a single call", async () => {
    render(
      <TurnCost
        turn={{ turn_id: "r", usage: { prompt_tokens: 10, completion_tokens: 2, cost_usd: 0.0001 }, by_role: [role("guard", 10, 2, 0.0001)] }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "12 tokens · $0.0001 · 1 step" }));
    expect(screen.getByRole("table")).toHaveTextContent("1 call");
  });

  it("renders nothing for a turn without calls", () => {
    const { container } = render(
      <TurnCost turn={{ turn_id: "r", usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 }, by_role: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TurnCost unpriced calls", () => {
  const jev = { ...turn, by_role: turn.by_role.map((r) => (r.role === "router" ? { ...r, cost_usd: 0, unpriced_calls: 1 } : r)) };

  it("router step not priced", async () => {
    render(<TurnCost turn={jev} />);
    const button = screen.getByRole("button", { name: /\(excludes 1 unpriced call\)/ });
    expect(button).toHaveTextContent("9,211 tokens · $0.0063 · 4 steps (excludes 1 unpriced call)");
    await userEvent.click(button);
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    const router = rows.find((r) => r.textContent?.startsWith("Router"))!;
    expect(router).toHaveTextContent("not priced");
    expect(router).not.toHaveTextContent("$");
    expect(rows.at(-1)).toHaveTextContent("(excludes 1 unpriced call)");
  });

  it("a step with priced and unpriced calls shows its figure and + not priced", async () => {
    const mixed = { ...turn, by_role: turn.by_role.map((r) => (r.role === "router" ? { ...r, calls: 2, unpriced_calls: 1 } : r)) };
    render(<TurnCost turn={mixed} />);
    await userEvent.click(screen.getByRole("button", { name: /excludes 1 unpriced call/ }));
    const router = within(screen.getByRole("table")).getAllByRole("row").find((r) => r.textContent?.startsWith("Router"))!;
    expect(router).toHaveTextContent("$0.0003 + not priced");
  });

  it("says nothing about unpriced calls when there are none", () => {
    render(<TurnCost turn={turn} />);
    expect(screen.queryByText(/priced/)).toBeNull();
  });
});

describe("TurnCost fallback notes", () => {
  it("says which model failed and which fallback answered", () => {
    const f = { role: "agent", model: "anthropic/claude-haiku-5.5", replaced: "openai/gpt-6-luna", reason: "gone 404: No endpoints found", ok: true };
    render(<TurnCost turn={{ ...turn, fallbacks: [f, f] }} />);
    const [note] = screen.getAllByRole("note");
    expect(note).toHaveTextContent(
      "Chat: openai/gpt-6-luna failed (gone 404: No endpoints found), so the fallback model anthropic/claude-haiku-5.5 answered.",
    );
    expect(screen.getAllByRole("note")).toHaveLength(1); // the same pair twice is one note
  });

  it("says when the fallback failed too", () => {
    const f = { role: "judge", model: "anthropic/claude-haiku-5.5", replaced: "openai/gpt-6-luna", reason: "down 502", ok: false };
    render(<TurnCost turn={{ ...turn, fallbacks: [f] }} />);
    expect(screen.getByRole("note")).toHaveTextContent("Check: openai/gpt-6-luna failed (down 502), and the fallback model anthropic/claude-haiku-5.5 failed too.");
  });
});
