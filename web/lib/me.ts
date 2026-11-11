"use client";

import { useQuery } from "@tanstack/react-query";
import { getMe } from "./api";
import type { Me } from "./types";

export const ME_KEY = ["me"] as const;

/** The signed-in account: budget, spend, admin flag, last world. `undefined` until it loads. */
export function useMe(): Me | undefined {
  return useQuery({ queryKey: ME_KEY, queryFn: getMe }).data;
}

const usd = (n: number) => n.toFixed(2);

/** The header's spend line: no limit shown for the admin. */
export function spendLine(me: Me): string {
  return me.monthly_budget_usd === null
    ? `This month: $${usd(me.month_spend_usd)}`
    : `This month: $${usd(me.month_spend_usd)} of $${usd(me.monthly_budget_usd)}`;
}

/** The API's 402 wording, for showing it before a request is made (the server stays the authority). */
export function overBudgetMessage(me: Me | undefined): string | null {
  if (!me?.over_budget || me.monthly_budget_usd === null) return null;
  return `You've used this month's AI budget ($${usd(me.monthly_budget_usd)}). It resets on ${me.budget_resets_on}.`;
}
