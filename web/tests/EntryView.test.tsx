import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EntryView } from "@/components/EntryView";
import { getEntries, getEntry, getMentions } from "@/lib/api";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { Entry } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));
vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    constructor(public status: number) {
      super("x");
    }
  }
  return { getEntry: vi.fn(), getEntries: vi.fn(), getMentions: vi.fn(), ApiError };
});

const entry = (over: Partial<Entry>): Entry => ({
  id: "ent_0001", world_id: "w1", title: "Ister", type: "place", body: "A river city.", status: "canon",
  source: "user", source_url: null, licence: null, trusted: true, aliases: [], links: [], facts: [],
  version: 1, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z", ...over,
});
const renderIt = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EntryView entryId="ent_0001" />
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.mocked(getEntry).mockReset();
  vi.mocked(getMentions).mockReset();
  vi.mocked(getEntries).mockReset().mockResolvedValue([]);
  vi.mocked(getMentions).mockResolvedValue([]);
  sessionStorage.clear();
});

describe("EntryView imported-text marker", () => {
  it("flags an untrusted entry and lists each imported section", async () => {
    vi.mocked(getEntry).mockResolvedValue(
      entry({
        trusted: false,
        body: "A river city.\n\n## Imported from a.md (2026-11-05)\nOne.\n\n## Imported from paste (2026-11-06)\nTwo.",
      }),
    );
    renderIt();
    expect(await screen.findByText("Contains imported text")).toBeInTheDocument();
    expect(screen.getByText("a.md (2026-11-05)")).toBeInTheDocument();
    expect(screen.getByText("paste (2026-11-06)")).toBeInTheDocument();
  });

  it("shows nothing for a trusted entry", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ body: "A river city.\n\n## Imported from a.md (2026-11-05)\nOne." }));
    renderIt();
    await screen.findByRole("heading", { name: "Ister" });
    expect(screen.queryByText("Contains imported text")).toBeNull();
    expect(screen.queryByText("a.md (2026-11-05)")).toBeNull();
  });
});

describe("EntryView secrets", () => {
  const secretEntry = () =>
    entry({
      status: "secret",
      facts: [{ key: "Vault", value: "Under the bell", refs: [], status: "canon", told_by: null }],
    });
  const secretFact = [{ key: "Mayor", value: "Choir member", refs: [], status: "secret" as const, told_by: null }];

  it("hides a secret entry until Show, which works with the world toggle off", async () => {
    vi.mocked(getEntry).mockResolvedValue(secretEntry());
    renderIt();
    expect(await screen.findByText("Secret entry")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(screen.getByRole("heading", { name: "Ister" })).toBeInTheDocument();
  });

  it("shows a secret entry when the world toggle is on", async () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    vi.mocked(getEntry).mockResolvedValue(secretEntry());
    renderIt();
    expect(await screen.findByRole("heading", { name: "Ister" })).toBeInTheDocument();
    expect(screen.getByText("Under the bell")).toBeInTheDocument();
  });

  it("hides a secret fact until its Show, which works with the toggle off", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ facts: secretFact }));
    renderIt();
    await screen.findByRole("heading", { name: "Ister" });
    expect(screen.queryByText("Choir member")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact" }));
    expect(screen.getByText("Choir member")).toBeInTheDocument();
  });

  it("shows a secret fact when the world toggle is on", async () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    vi.mocked(getEntry).mockResolvedValue(entry({ facts: secretFact }));
    renderIt();
    expect(await screen.findByText("Choir member")).toBeInTheDocument();
  });
});

describe("EntryView full page", () => {
  it("renders one card per section and a placeholder for an empty Description", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ body: "Intro.\n\n## History\nOld." }));
    renderIt();
    expect(await screen.findByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Description" })).toBeInTheDocument();
    expect(screen.getByText("Old.")).toBeInTheDocument();
  });

  it("shows No description yet. for an empty body", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ body: "" }));
    renderIt();
    expect(await screen.findByText("No description yet.")).toBeInTheDocument();
  });

  it("lists mentions as chips linking to the entry, masking secret ones", async () => {
    vi.mocked(getMentions).mockResolvedValue([
      { id: "ent_0002", title: "Bell Tower", type: "place", status: "canon" },
      { id: "ent_0019", title: "The Choir Ledger", type: "item", status: "secret" },
    ]);
    vi.mocked(getEntry).mockResolvedValue(entry({}));
    renderIt();
    const link = await screen.findByRole("link", { name: /Bell Tower/ });
    expect(link).toHaveAttribute("href", "/canon/ent_0002");
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.queryByRole("link", { name: /Choir/ })).toBeNull();
  });

  it("reveals secret mentions when the world toggle is on", async () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    vi.mocked(getMentions).mockResolvedValue([
      { id: "ent_0019", title: "The Choir Ledger", type: "item", status: "secret" },
    ]);
    vi.mocked(getEntry).mockResolvedValue(entry({}));
    renderIt();
    expect(await screen.findByRole("link", { name: /The Choir Ledger/ })).toHaveAttribute("href", "/canon/ent_0019");
  });

  it("says when nothing mentions the entry", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({}));
    renderIt();
    expect(await screen.findByText("No other entries mention it.")).toBeInTheDocument();
  });

  it("does not fetch mentions for a hidden secret entry", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ status: "secret" }));
    renderIt();
    await screen.findByText("This entry is hidden so the screen is safe to share.");
    expect(getMentions).not.toHaveBeenCalled();
  });

  it("shows provenance for each source", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({}));
    const a = renderIt();
    expect(await screen.findByText("Source: your notes")).toBeInTheDocument();
    a.unmount();

    vi.mocked(getEntry).mockResolvedValue(entry({ source: "reference", source_url: "https://en.wikipedia.org/wiki/X" }));
    const b = renderIt();
    expect(await screen.findByText(/Source: Wikipedia reference/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "https://en.wikipedia.org/wiki/X" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    b.unmount();

    vi.mocked(getEntry).mockResolvedValue(
      entry({ source: "official", source_url: "https://x.example/c", licence: "CC-BY" }),
    );
    renderIt();
    const el = await screen.findByText(/Source: official canon/);
    expect(el.textContent).toBe("Source: official canon · https://x.example/c · Licence CC-BY");
  });

  it("shows a non-http source_url as text, never as a link", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ source: "reference", source_url: "javascript:alert(1)" }));
    renderIt();
    expect(await screen.findByText("javascript:alert(1)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "javascript:alert(1)" })).toBeNull();
  });

  it("flags an untrusted source", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ trusted: false }));
    renderIt();
    expect(await screen.findByText("Untrusted source")).toBeInTheDocument();
  });

  it("marks a whole untrusted entry with no import headings as imported", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ trusted: false }));
    renderIt();
    expect(await screen.findByText("Contains imported text")).toBeInTheDocument();
    expect(screen.getByText("the whole entry")).toBeInTheDocument();
  });

  it("keeps the version and edited line", async () => {
    vi.mocked(getEntry).mockResolvedValue(entry({ version: 3 }));
    renderIt();
    expect(await screen.findByText(/v3 · edited/)).toBeInTheDocument();
  });

  it("does not mark an untrusted reference entry as wholly imported", async () => {
    vi.mocked(getEntry).mockResolvedValue(
      entry({ trusted: false, source: "reference", source_url: "https://en.wikipedia.org/wiki/X" }),
    );
    renderIt();
    expect(await screen.findByText("Untrusted source")).toBeInTheDocument();
    expect(screen.getByText(/Source: Wikipedia reference/)).toBeInTheDocument();
    expect(screen.queryByText("Contains imported text")).toBeNull();
  });

  it("says when mentions could not be loaded", async () => {
    vi.mocked(getMentions).mockRejectedValue(new Error("x"));
    vi.mocked(getEntry).mockResolvedValue(entry({}));
    renderIt();
    expect(await screen.findByText("Could not load mentions.")).toBeInTheDocument();
  });
});

describe("EntryView fact refs", () => {
  it("renders a fact ref as a chip to the referenced entry", async () => {
    vi.mocked(getEntries).mockResolvedValue([
      entry({ id: "ent_0004", title: "Ashen Choir", type: "faction" }),
    ]);
    vi.mocked(getEntry).mockResolvedValue(
      entry({ facts: [{ key: "Sings to", value: "Ister", refs: ["ent_0004"], status: "canon", told_by: null }] }),
    );
    renderIt();
    expect(await screen.findByRole("link", { name: /Ashen Choir/ })).toHaveAttribute("href", "/canon/ent_0004");
  });

  it("a locally revealed secret entry still masks a secret ref", async () => {
    vi.mocked(getEntries).mockResolvedValue([
      entry({ id: "ent_0004", title: "Ashen Choir", type: "faction" }),
      entry({ id: "ent_0019", title: "The Choir Ledger", type: "item", status: "secret" }),
    ]);
    vi.mocked(getEntry).mockResolvedValue(
      entry({
        status: "secret",
        facts: [{ key: "Keeps", value: "A ledger", refs: ["ent_0004", "ent_0019"], status: "canon", told_by: null }],
      }),
    );
    renderIt();
    await userEvent.click(await screen.findByRole("button", { name: "Show" }));
    expect(screen.getByRole("heading", { name: "Ister" })).toBeInTheDocument();
    // The page's own Show reveals this entry only: the other secret entry's ref stays out.
    expect(await screen.findByRole("link", { name: /Ashen Choir/ })).toBeInTheDocument();
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(document.querySelector('a[href="/canon/ent_0019"]')).toBeNull();
  });
});
