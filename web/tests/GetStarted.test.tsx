import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GetStarted } from "@/components/GetStarted";
import { TOUR_KEYS } from "@/lib/tour";
import type { World } from "@/lib/types";

const demo: World = { id: "w_velmar", name: "Velmar", is_demo: true, divergent: false, owner_id: "user_a" };
const own: World = { id: "w_2", name: "My World", is_demo: false, divergent: false, owner_id: "user_a" };

describe("GetStarted", () => {
  it("ticks steps from localStorage and hides after dismiss", async () => {
    localStorage.setItem(TOUR_KEYS.visited, "1");
    localStorage.setItem(TOUR_KEYS.chatted, "1");
    render(<GetStarted world={demo} onStartOwn={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(4));
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(/done/i);
    expect(items[1]).toHaveTextContent(/done/i);
    expect(items[2]).not.toHaveTextContent(/done/i);
    expect(items[3]).not.toHaveTextContent(/done/i);

    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(screen.queryByText(/get started/i)).toBeNull();
    expect(localStorage.getItem(TOUR_KEYS.dismissed)).toBe("1");
  });

  it("stays hidden once dismissed and for non-demo worlds", () => {
    const { unmount } = render(<GetStarted world={own} onStartOwn={vi.fn()} />);
    expect(screen.queryByText(/get started/i)).toBeNull();
    unmount();
    localStorage.setItem(TOUR_KEYS.dismissed, "1");
    render(<GetStarted world={demo} onStartOwn={vi.fn()} />);
    expect(screen.queryByText(/get started/i)).toBeNull();
  });

  it("Start my own world calls the handler", async () => {
    const onStartOwn = vi.fn();
    render(<GetStarted world={demo} onStartOwn={onStartOwn} />);
    await userEvent.click(await screen.findByRole("button", { name: /start my own world/i }));
    expect(onStartOwn).toHaveBeenCalledOnce();
  });
});
