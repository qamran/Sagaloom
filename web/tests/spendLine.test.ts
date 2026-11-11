import { describe, expect, it } from "vitest";
import { overBudgetMessage, spendLine } from "@/lib/me";
import { TOUR_KEYS, setTourUser } from "@/lib/tour";
import type { Me } from "@/lib/types";

const me = (over: Partial<Me> = {}): Me => ({
  id: "user_a", email: "a@b.c", display_name: "A", is_admin: false, last_world_id: null,
  month_spend_usd: 0.2345, monthly_budget_usd: 1, budget_resets_on: "2026-12-01", over_budget: false, ...over,
});

describe("spendLine", () => {
  it("shows spend of the budget with two decimals", () => {
    expect(spendLine(me())).toBe("This month: $0.23 of $1.00");
  });
  it("shows only the spend for the admin", () => {
    expect(spendLine(me({ monthly_budget_usd: null, is_admin: true }))).toBe("This month: $0.23");
  });
});

describe("overBudgetMessage", () => {
  it("is null while under budget, the API's wording once over", () => {
    expect(overBudgetMessage(me())).toBeNull();
    expect(overBudgetMessage(undefined)).toBeNull();
    expect(overBudgetMessage(me({ over_budget: true, month_spend_usd: 1.02 }))).toBe(
      "You've used this month's AI budget ($1.00). It resets on 2026-12-01.",
    );
  });
});

describe("tour keys", () => {
  it("carry the user id once it is set", () => {
    setTourUser("user_a");
    expect(TOUR_KEYS.dismissed).toBe("sagaloom.tour.user_a.dismissed");
    setTourUser(null);
    expect(TOUR_KEYS.dismissed).toBe("sagaloom.tour.dismissed");
  });
});
