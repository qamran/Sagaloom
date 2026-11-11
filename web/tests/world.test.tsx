import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, getWorlds, putMe } from "@/lib/api";
import { TOUR_KEYS } from "@/lib/tour";
import type { Me, World } from "@/lib/types";
import { useWorld, WorldProvider } from "@/lib/world";
import { Providers } from "@/components/Providers";

const auth = vi.hoisted(() => ({
  value: { isLoaded: true, isSignedIn: true as boolean | undefined, userId: "user_a" as string | null | undefined },
}));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => auth.value }));
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
  return (
    <>
      <p data-testid="active">{w.world?.id ?? "none"}</p>
      <p data-testid="loading">{String(w.isLoading)}</p>
      <p data-testid="worlds">{w.worlds.map((x) => x.id).join(",")}</p>
    </>
  );
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
  auth.value = { isLoaded: true, isSignedIn: true, userId: "user_a" };
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

  it("is loading, not empty, until Clerk has loaded", async () => {
    auth.value = { isLoaded: false, isSignedIn: undefined, userId: undefined };
    const view = setup();
    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    expect(screen.getByTestId("active")).toHaveTextContent("none");
    expect(getWorlds).not.toHaveBeenCalled();

    auth.value = { isLoaded: true, isSignedIn: true, userId: "user_a" };
    view.rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <WorldProvider>
          <Probe />
        </WorldProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
  });
});

describe("Providers across a Clerk user change", () => {
  const app = () => (
    <Providers>
      <Probe />
    </Providers>
  );

  it("drops the previous user's data and picked world before the new user's queries answer", async () => {
    const view = render(app());
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
    act(() => handle.current?.setWorldId("other"));
    expect(TOUR_KEYS.visited).toBe("sagaloom.tour.user_a.visited");

    // User B signs in without a page load; B's queries have not answered yet. (This browser's stored
    // pick is cleared so only the in-memory one is tested; real world ids differ between accounts.)
    localStorage.removeItem("sagaloom.world");
    let answerWorlds!: (w: World[]) => void;
    let answerMe!: (m: Me) => void;
    vi.mocked(getWorlds).mockReturnValue(new Promise((r) => (answerWorlds = r)));
    vi.mocked(getMe).mockReturnValue(new Promise((r) => (answerMe = r)));
    auth.value = { isLoaded: true, isSignedIn: true, userId: "user_b" };
    view.rerender(app());

    expect(screen.getByTestId("worlds")).toBeEmptyDOMElement();
    expect(screen.getByTestId("active")).toHaveTextContent("none");
    expect(screen.getByTestId("loading")).toHaveTextContent("true");

    await act(async () => {
      answerWorlds([w("b-velmar"), w("other")]);
      answerMe({ ...me(null), id: "user_b" });
    });
    // A's pick ("other") is not carried over: B starts in B's first world.
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("b-velmar"));
    expect(TOUR_KEYS.visited).toBe("sagaloom.tour.user_b.visited");
  });

  it("keeps what was fetched while Clerk finished its first load", async () => {
    auth.value = { isLoaded: false, isSignedIn: undefined, userId: undefined };
    const view = render(app());
    auth.value = { isLoaded: true, isSignedIn: true, userId: "user_a" };
    view.rerender(app());
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("mine"));
    expect(getWorlds).toHaveBeenCalledTimes(1);
  });
});
