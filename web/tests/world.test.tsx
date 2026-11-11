import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, getWorlds, putMe } from "@/lib/api";
import { TOUR_KEYS } from "@/lib/tour";
import type { Me, World } from "@/lib/types";
import { useWorld, WorldProvider } from "@/lib/world";

vi.mock("@clerk/nextjs", () => ({ useAuth: () => ({ isLoaded: true, isSignedIn: true }) }));
vi.mock("@/lib/api", () => ({ getWorlds: vi.fn(), getMe: vi.fn(), putMe: vi.fn(), createWorld: vi.fn() }));

const w = (id: string): World => ({ id, name: id, is_demo: false, divergent: false, owner_id: "user_a" });
const me = (last: string | null): Me => ({
  id: "user_a", email: "a@b.c", display_name: "A", is_admin: false, last_world_id: last,
  month_spend_usd: 0, monthly_budget_usd: 1, budget_resets_on: "2026-12-01", over_budget: false,
});

const handle: { current: ReturnType<typeof useWorld> | null } = { current: null };
function Probe() {
  const w = useWorld();
  useEffect(() => {
    handle.current = w;
  });
  return <p data-testid="active">{w.world?.id ?? "none"}</p>;
}
const setup = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WorldProvider>
        <Probe />
      </WorldProvider>
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.mocked(getWorlds).mockReset().mockResolvedValue([w("velmar-ab12"), w("mine"), w("other")]);
  vi.mocked(getMe).mockReset().mockResolvedValue(me("mine"));
  vi.mocked(putMe).mockReset().mockResolvedValue(me("other"));
});

describe("WorldProvider", () => {
  it("starts in the world the account last used", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
  });

  it("ignores a last world that is not one of the user's worlds", async () => {
    vi.mocked(getMe).mockResolvedValue(me("someone-elses"));
    localStorage.setItem("sagaloom.world", "other");
    setup();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("other"));
  });

  it("falls back to the first world, never a hardcoded velmar", async () => {
    vi.mocked(getMe).mockResolvedValue(me(null));
    setup();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("velmar-ab12"));
  });

  it("tells the API when the author switches worlds", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
    act(() => handle.current?.setWorldId("other"));
    expect(screen.getByTestId("active")).toHaveTextContent("other");
    await waitFor(() => expect(putMe).toHaveBeenCalledWith("other"));
  });

  it("keys the Get Started flags by user id", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
    expect(TOUR_KEYS.visited).toBe("sagaloom.tour.user_a.visited");
  });
});
