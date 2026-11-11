import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "@/components/home/HomePage";
import type { PublicPreview } from "@/lib/types";

// The home page runs signed out: no world, no API client. Anything that tried to fetch would fail here.
vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: null }) }));
vi.mock("@/lib/api", () => ({}));

const { authMock, redirectMock, getPreviewMock } = vi.hoisted(() => ({
  authMock: vi.fn(),
  redirectMock: vi.fn((to: string) => {
    throw new Error(`NEXT_REDIRECT ${to}`);
  }),
  getPreviewMock: vi.fn(),
}));
vi.mock("@clerk/nextjs/server", () => ({ auth: authMock }));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/preview", () => ({ getPreview: getPreviewMock }));

import Home from "../app/page";

// The API's own fixture, so the page is tested against what it will really be served.
const preview = JSON.parse(
  readFileSync(join(__dirname, "..", "..", "api", "sagaloom", "public", "preview.json"), "utf8"),
) as PublicPreview;

const GITHUB = "https://github.com/qamran/Sagaloom";

describe("HomePage", () => {
  it("shows the hero promise, the audience and both buttons", () => {
    render(<HomePage preview={preview} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "A continuity editor for your fictional world: you decide, it checks." }),
    ).toBeInTheDocument();
    expect(screen.getByText("For authors, fan-fiction writers and solo game masters.")).toBeInTheDocument();
    const hero = screen.getByRole("region", { name: /continuity editor/ });
    expect(within(hero).getByRole("link", { name: "Sign up free" })).toHaveAttribute("href", "/sign-up");
    expect(within(hero).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("walks the loop in four steps, in order", () => {
    render(<HomePage preview={preview} />);
    const loop = screen.getByRole("list", { name: "The loop" });
    expect(within(loop).getAllByRole("listitem").map((li) => li.querySelector("h3")?.textContent)).toEqual([
      "You state a fact",
      "Sagaloom checks it against canon",
      "You approve, edit, reject or save it as a myth",
      "It becomes canon",
    ]);
  });

  it("shows the author's message and the recorded card: Conflict citing ent_0012, actions disabled", () => {
    render(<HomePage preview={preview} />);
    const section = screen.getByRole("region", { name: /See it catch a contradiction/ });
    expect(within(section).getByText("Velmar has three moons that rise together at the solstice.")).toBeInTheDocument();
    const card = within(section).getByRole("region", { name: "Review proposal: Sky of Velmar" });
    expect(within(within(card).getByRole("list", { name: "Check result" })).getByText("Conflict")).toBeInTheDocument();
    expect(within(card).getAllByText("ent_0012").length).toBeGreaterThan(0);
    // Both sides of the clash, from the flags' facts (the fixture has no quotes).
    expect(within(card).getByText("Only light in the night sky: Ister")).toBeInTheDocument();
    expect(within(card).getAllByText("Three").length).toBeGreaterThan(0);
    const buttons = within(card).getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(4);
    for (const b of buttons) expect(b).toBeDisabled();
    expect(within(card).getByText("Sign up to try it on your own world")).toBeInTheDocument();
  });

  it("opens the preview entries read-only; refs outside the preview are plain text", async () => {
    render(<HomePage preview={preview} />);
    const entries = screen.getByRole("region", { name: "Velmar entries" });
    await userEvent.click(within(entries).getByRole("button", { name: /Lantern Quay/ }));
    const reader = within(entries).getByRole("article");
    expect(within(reader).getByRole("heading", { name: "Lantern Quay" })).toBeInTheDocument();
    expect(within(reader).queryByRole("textbox")).toBeNull();
    expect(within(reader).queryByRole("link")).toBeNull();
    // ent_0011 is not in the preview: its id is text, not something to open.
    expect(within(reader).getByText("ent_0011")).toBeInTheDocument();
    expect(within(reader).queryByRole("button", { name: /ent_0011/ })).toBeNull();

    // A ref to an entry that is in the preview opens it.
    await userEvent.click(within(entries).getByRole("button", { name: /Sky of Velmar/ }));
    await userEvent.click(within(within(entries).getByRole("article")).getAllByRole("button", { name: /Ister, the red moon/ })[0]);
    expect(within(within(entries).getByRole("article")).getByRole("heading", { name: "Ister, the red moon" })).toBeInTheDocument();
  });

  it("links into no app page: only sign-in, sign-up and GitHub", () => {
    render(<HomePage preview={preview} />);
    const hrefs = [...document.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) expect(["/sign-up", "/sign-in", GITHUB]).toContain(href);
  });

  it("lists the features and the first three README comparison rows with the caveat and date", () => {
    render(<HomePage preview={preview} />);
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(
      expect.arrayContaining(["Contradiction check on every change", "Human approval before anything is written"]),
    );
    const table = screen.getByRole("table", { name: /How Sagaloom compares/ });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Feature",
      "Sagaloom",
      "Realmweaver",
      "LitMemo",
      "StoryGuard",
    ]);
    expect(within(table).getAllByRole("rowheader").map((th) => th.textContent)).toEqual([
      "Fact-level contradiction check",
      "Human approval before any write",
      "Import with verbatim text",
    ]);
    expect(screen.getByText(/means we found no mention of it on the vendor's public pages \(checked 2026-11-04\)/)).toBeInTheDocument();
  });

  it("ends with the data statement, the GitHub link and the sign-up buttons again", () => {
    render(<HomePage preview={preview} />);
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByText("Your canon stays on the server you run it on.")).toBeInTheDocument();
    expect(within(footer).getByRole("link", { name: /GitHub/ })).toHaveAttribute("href", GITHUB);
    expect(within(footer).getByRole("link", { name: "Sign up free" })).toHaveAttribute("href", "/sign-up");
    expect(within(footer).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("renders without the preview when it could not be loaded", () => {
    render(<HomePage preview={null} />);
    expect(screen.getByText("Preview unavailable right now.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Review proposal/ })).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("falls back to 'Preview unavailable' when the recorded card cannot render", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const pid = preview.pending_interrupt.proposals[0].proposal_id;
    const broken = {
      ...preview,
      pending_interrupt: { ...preview.pending_interrupt, checks: { [pid]: { ...preview.pending_interrupt.checks[pid], flags: null } } },
    } as unknown as PublicPreview;
    render(<HomePage preview={broken} />);
    expect(screen.getByText("Preview unavailable right now.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    vi.mocked(console.error).mockRestore();
  });

  it("marks the hero's sample card as an illustration, worded like the real card", () => {
    render(<HomePage preview={preview} />);
    const hero = screen.getByRole("region", { name: /continuity editor/ });
    expect(within(hero).getByText(/An illustration/)).toBeInTheDocument();
    expect(within(hero).getByText("Approve anyway")).toBeInTheDocument();
    expect(within(hero).queryByRole("button")).toBeNull();
  });

  it("words the Sagaloom comparison cells for visitors, not developers", () => {
    render(<HomePage preview={preview} />);
    const table = screen.getByRole("table", { name: /How Sagaloom compares/ });
    expect(within(table).getByText("Always: nothing is written until you approve, edit, reject or save it as a myth")).toBeInTheDocument();
    expect(table.textContent).not.toMatch(/interrupt\(\)|commit` node|node writes/);
  });

  it("keeps headings in order: one h1, then h2 sections", () => {
    render(<HomePage preview={preview} />);
    const levels = [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((h) => Number(h.tagName[1]));
    expect(levels.filter((l) => l === 1)).toHaveLength(1);
    expect(levels[0]).toBe(1);
    levels.forEach((l, i) => i > 0 && expect(l - levels[i - 1]).toBeLessThanOrEqual(1));
  });
});

describe("the / route", () => {
  beforeEach(() => {
    authMock.mockReset();
    redirectMock.mockClear();
    getPreviewMock.mockReset();
  });

  it("sends a signed-in author to Canon without loading the preview", async () => {
    authMock.mockResolvedValue({ userId: "user_1" });
    await expect(Home()).rejects.toThrow("NEXT_REDIRECT /canon");
    expect(redirectMock).toHaveBeenCalledWith("/canon");
    expect(getPreviewMock).not.toHaveBeenCalled();
  });

  it("shows a signed-out visitor the home page with the preview", async () => {
    authMock.mockResolvedValue({ userId: null });
    getPreviewMock.mockResolvedValue(preview);
    render(await Home());
    expect(redirectMock).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "Review proposal: Sky of Velmar" })).toBeInTheDocument();
  });

  it("still shows the home page when the preview is unavailable", async () => {
    authMock.mockResolvedValue({ userId: null });
    getPreviewMock.mockResolvedValue(null);
    render(await Home());
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Preview unavailable right now.")).toBeInTheDocument();
  });
});
