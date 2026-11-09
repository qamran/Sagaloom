import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImportPage from "@/app/import/page";
import type { ImportRun } from "@/lib/useImport";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));
vi.mock("@/components/RecentImports", () => ({ RecentImports: () => null }));
vi.mock("@/components/ImportProgress", () => ({ ImportProgress: () => <p>Extracting…</p> }));

const FAILED = "The extraction could not run, so nothing was imported. Try again.";
let run: ImportRun;
vi.mock("@/lib/useImport", () => ({ useImport: () => run }));

const runOf = (over: Partial<ImportRun> = {}): ImportRun => ({
  phase: "idle", candidates: null, skipped: null, events: [], worldId: null, error: null, start: vi.fn(async () => undefined), ...over,
});

beforeEach(() => {
  run = runOf();
});

describe("ImportPage", () => {
  it("keeps the pasted text after a failed import, ready to try again", async () => {
    const { rerender } = render(<ImportPage />);
    await userEvent.type(screen.getByLabelText("Text to import"), "Ister has two moons.");
    const paste = () => within(screen.getByRole("region", { name: "Paste text" }));
    await userEvent.click(paste().getByRole("button", { name: "Extract entries" }));
    expect(run.start).toHaveBeenCalledWith("w1", { text: "Ister has two moons." });

    run = runOf({ phase: "extracting" });
    rerender(<ImportPage />);
    expect(screen.getByText("Extracting…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Extract entries" })).toBeNull(); // hidden while running

    run = runOf({ phase: "error", error: FAILED });
    rerender(<ImportPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(FAILED);
    expect(screen.getByLabelText("Text to import")).toHaveValue("Ister has two moons.");
    expect(paste().getByRole("button", { name: "Extract entries" })).toBeEnabled();
  });
});
