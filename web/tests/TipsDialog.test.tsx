import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TipsDialog } from "@/components/TipsDialog";
import { shuffled, TIPS, TIPS_SESSION_KEY } from "@/lib/tips";

const auth = vi.hoisted(() => ({ value: { userId: "user_a" as string | null } }));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => auth.value }));

const HIDDEN = "sagaloom.tips.user_a.hidden";
const tipText = () => screen.getByRole("dialog").querySelector("p")!.textContent!;

beforeEach(() => {
  auth.value = { userId: "user_a" };
});

describe("TipsDialog", () => {
  it("opens at startup with tip 1 of all tips, and steps forward and back, wrapping round", async () => {
    render(<TipsDialog />);
    expect(await screen.findByRole("heading", { name: `Useful tips 1/${TIPS.length}` })).toBeInTheDocument();
    const first = tipText();
    expect(TIPS).toContain(first);

    await userEvent.click(screen.getByRole("button", { name: "Next tip" }));
    expect(screen.getByRole("heading", { name: `Useful tips 2/${TIPS.length}` })).toBeInTheDocument();
    expect(tipText()).not.toBe(first);

    await userEvent.click(screen.getByRole("button", { name: "Previous tip" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous tip" }));
    expect(screen.getByRole("heading", { name: `Useful tips ${TIPS.length}/${TIPS.length}` })).toBeInTheDocument();
  });

  it("closes with the close button and with Escape", async () => {
    const { unmount } = render(<TipsDialog />);
    await userEvent.click(await screen.findByRole("button", { name: "Close tips" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    unmount();

    sessionStorage.clear();
    render(<TipsDialog />);
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes with Got it", async () => {
    render(<TipsDialog />);
    await userEvent.click(await screen.findByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows once per browser session, not on every page", async () => {
    const { unmount } = render(<TipsDialog />);
    await screen.findByRole("dialog");
    expect(sessionStorage.getItem(TIPS_SESSION_KEY)).toBe("1");
    unmount();
    render(<TipsDialog />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("never shows again for this account once Don't show this again is ticked; unticking undoes it", async () => {
    render(<TipsDialog />);
    const box = await screen.findByRole("checkbox", { name: "Don't show this again" });
    await userEvent.click(box);
    expect(localStorage.getItem(HIDDEN)).toBe("1");
    await userEvent.click(box);
    expect(localStorage.getItem(HIDDEN)).toBeNull();
  });

  it("stays closed for an account that opted out, but still shows for another account", async () => {
    localStorage.setItem(HIDDEN, "1");
    const { unmount } = render(<TipsDialog />);
    expect(screen.queryByRole("dialog")).toBeNull();
    unmount();
    auth.value = { userId: "user_b" };
    render(<TipsDialog />);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("waits until the account is known", () => {
    auth.value = { userId: null };
    render(<TipsDialog />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(sessionStorage.getItem(TIPS_SESSION_KEY)).toBeNull();
  });
});

describe("shuffled", () => {
  it("returns every tip exactly once, in an order set by the random source", () => {
    const out = shuffled(TIPS, () => 0);
    expect([...out].sort()).toEqual([...TIPS].sort());
    expect(out).not.toEqual(TIPS);
    expect(TIPS).toHaveLength(27);
  });
});
