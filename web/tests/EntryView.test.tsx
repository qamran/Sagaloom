import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EntryView } from "@/components/EntryView";
import { getEntry } from "@/lib/api";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { Entry } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));
vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    constructor(public status: number) {
      super("x");
    }
  }
  return { getEntry: vi.fn(), ApiError };
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
