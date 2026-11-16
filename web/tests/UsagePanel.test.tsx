import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UsagePanel } from "@/components/UsagePanel";
import type { Me, StudioData } from "@/lib/types";

const usage: StudioData["usage"] = { prompt_tokens: 1, completion_tokens: 2, cost_usd: 0.01, by_model: [] };
const me: Me = {
  id: "u", email: "a@b.c", display_name: "A", is_admin: true, last_world_id: null,
  month_spend_usd: 0.2345, monthly_budget_usd: null, budget_resets_on: "2026-12-01", over_budget: false,
};

describe("UsagePanel", () => {
  it("has no All users switch unless given a handler (non-admin)", () => {
    render(<UsagePanel usage={usage} />);
    expect(screen.queryByRole("switch", { name: "All users" })).toBeNull();
  });

  it("usage row not priced", () => {
    const by_model = [
      { role: "router", model: "jev-latest", calls: 2, prompt_tokens: 80, completion_tokens: 6, cost_usd: 0, unpriced_calls: 2 },
      { role: "agent", model: "openai/gpt-6-luna", calls: 1, prompt_tokens: 10, completion_tokens: 2, cost_usd: 0.01 },
    ];
    render(<UsagePanel usage={{ ...usage, by_model }} />);
    expect(screen.getByText(/\$0\.0000 \+ not priced/)).toBeInTheDocument();
    expect(screen.getAllByText(/not priced/)).toHaveLength(1);
  });

  it("offers the admin an All users switch and the month's spend", async () => {
    const onScope = vi.fn();
    render(<UsagePanel usage={usage} me={me} scope="mine" onScope={onScope} />);
    expect(screen.getByText("This month: $0.23")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("switch", { name: "All users" }));
    expect(onScope).toHaveBeenCalledWith("all");
  });
});
