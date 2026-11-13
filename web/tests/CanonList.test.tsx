import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CanonList } from "@/components/CanonList";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { Entry } from "@/lib/types";

const params = vi.hoisted(() => ({ value: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/canon",
  useSearchParams: () => params.value,
}));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ world: { id: "w1", name: "Velmar", is_demo: true, divergent: false } }),
}));

const base = {
  world_id: "w1", body: "", source: "user", source_url: null, licence: null, trusted: true,
  aliases: [], links: [], facts: [], sources: [], version: 1, created_at: "", updated_at: "",
} as const;
const entries = [
  { ...base, id: "ent_0001", title: "Sky of Velmar", type: "place", status: "canon" },
  { ...base, id: "ent_0002", title: "The Mayor's Oath", type: "event", status: "secret" },
] as unknown as Entry[];

let list: Entry[] = entries;
vi.mock("@/lib/api", () => ({ getEntries: vi.fn(async () => list) }));
afterEach(() => {
  list = entries;
  params.value = new URLSearchParams();
  sessionStorage.clear();
});

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CanonList />
    </QueryClientProvider>,
  );
}

describe("CanonList secrets", () => {
  it("does not let search reveal or count-filter secret entries until shown", async () => {
    renderList();
    await screen.findByText("Sky of Velmar");
    expect(screen.queryByText(/Mayor/)).toBeNull();
    expect(screen.getByRole("button", { name: "Show 1 secret entry" })).toBeInTheDocument();

    // A query matching only the secret title: no results, and the hidden count is unchanged.
    await userEvent.type(screen.getByLabelText("Search entries"), "Mayor");
    expect(screen.getByText("No entries match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 1 secret entry" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show 1 secret entry" }));
    expect(screen.getByText(/Mayor/)).toBeInTheDocument();
  });
});

describe("CanonList world toggle", () => {
  const velmar = [
    ...Array.from({ length: 18 }, (_, i) => ({ ...base, id: `ent_${i + 1}`, title: `Entry ${i + 1}`, type: "place", status: "canon" })),
    { ...base, id: "ent_0019", title: "The Choir Ledger", type: "item", status: "secret" },
  ] as unknown as Entry[];

  it("lists 18 links, and 19 with the world toggle on", async () => {
    list = velmar;
    renderList();
    await screen.findByText("Entry 1");
    expect(screen.getAllByRole("link")).toHaveLength(18);
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    cleanup();
    renderList();
    await screen.findByText("The Choir Ledger");
    expect(screen.getAllByRole("link")).toHaveLength(19);
  });

  it("the sidebar button flips the same state", async () => {
    list = velmar;
    renderList();
    await userEvent.click(await screen.findByRole("button", { name: "Show 1 secret entry" }));
    expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w1"))).toBe("true");
    expect(screen.getByRole("button", { name: "Hide secret entries" })).toBeInTheDocument();
  });
});

describe("CanonList NC label", () => {
  const src = (nc: boolean) => ({
    kind: "official" as const, url: "https://en.wikipedia.org/wiki/Gandalf", licence: "CC BY-NC-SA 3.0",
    licence_url: null, nc, added_at: "2026-11-09",
  });

  it("labels an entry with a non-commercial source, and no other", async () => {
    list = [
      { ...base, id: "ent_0001", title: "Gandalf", type: "character", status: "canon", sources: [src(true)] },
      { ...base, id: "ent_0003", title: "Rivendell", type: "place", status: "canon", sources: [src(false)] },
    ] as unknown as Entry[];
    renderList();
    const nc = await screen.findByRole("link", { name: /Gandalf/ });
    expect(nc).toHaveTextContent(/NC$/);
    expect(screen.getByRole("link", { name: "Rivendell" })).not.toHaveTextContent("NC");
  });

  it("leaves a secret NC entry out of the list until shown, label and all", async () => {
    list = [
      { ...base, id: "ent_0004", title: "The Hidden Gate", type: "place", status: "secret", sources: [src(true)] },
      { ...base, id: "ent_0001", title: "Sky of Velmar", type: "place", status: "canon" },
    ] as unknown as Entry[];
    renderList();
    await screen.findByText("Sky of Velmar");
    expect(screen.queryByText("The Hidden Gate")).toBeNull();
    expect(screen.queryByText("NC")).toBeNull();
  });
});

describe("CanonList type dots", () => {
  it("gives each row a dot in its type colour", async () => {
    renderList();
    const link = await screen.findByRole("link", { name: /Sky of Velmar/ });
    expect(link.querySelector("[data-type-dot]")).toHaveClass("bg-place");
  });
});

describe("CanonList status filter", () => {
  const fact = (key: string, status: string) => ({
    key,
    value: "v",
    status,
    refs: [],
    told_by: null,
  });
  const world = [
    {
      ...base,
      id: "ent_0001",
      title: "Sky of Velmar",
      type: "place",
      status: "canon",
      facts: [fact("Moons", "canon")],
    },
    {
      ...base,
      id: "ent_0002",
      title: "The Song of Three Moons",
      type: "event",
      status: "myth",
    },
    {
      ...base,
      id: "ent_0003",
      title: "The Ashen Choir",
      type: "faction",
      status: "canon",
      facts: [fact("Founding", "myth"), fact("Allegiance", "secret")],
    },
    {
      ...base,
      id: "ent_0004",
      title: "The Choir Ledger",
      type: "item",
      status: "secret",
      facts: [fact("Origin", "myth")],
    },
  ] as unknown as Entry[];

  it("lists only myth entries and entries with myth facts, naming the facts, and keeps the filter on links", async () => {
    list = world;
    params.value = new URLSearchParams("status=myth");
    renderList();
    const song = await screen.findByRole("link", {
      name: /The Song of Three Moons/,
    });
    expect(song).toHaveAttribute("href", "/canon/ent_0002?status=myth");
    expect(
      screen.getByRole("link", { name: /The Ashen Choir/ }),
    ).toHaveTextContent("Founding · myth");
    expect(screen.queryByText("Sky of Velmar")).toBeNull();
    // A myth fact inside a secret entry stays hidden with the entry.
    expect(screen.queryByText(/Choir Ledger/)).toBeNull();
    expect(
      screen.getByRole("button", { name: "Show 1 secret entry" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Showing myths")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear filter" })).toHaveAttribute(
      "href",
      "/canon",
    );
  });

  it("hides every secret match, fact keys included, until secrets are shown", async () => {
    list = world;
    params.value = new URLSearchParams("status=secret");
    renderList();
    const show = await screen.findByRole("button", { name: "Show 2 secrets" });
    expect(
      screen.getByText("Secrets are hidden until you show them."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Allegiance/)).toBeNull();
    await userEvent.click(show);
    expect(
      screen.getByRole("link", { name: /The Ashen Choir/ }),
    ).toHaveTextContent("Allegiance · secret");
    expect(
      screen.getByRole("link", { name: /The Choir Ledger/ }),
    ).toBeInTheDocument();
  });

  it("says when the world has none, and ignores an unknown status", async () => {
    list = world;
    params.value = new URLSearchParams("status=rumour");
    renderList();
    expect(
      await screen.findByText("No rumours in this world."),
    ).toBeInTheDocument();
    cleanup();
    params.value = new URLSearchParams("status=canon");
    renderList();
    expect(await screen.findByText("Sky of Velmar")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing/)).toBeNull();
  });
});

describe("CanonList collapsible groups", () => {
  const mixed = [
    {
      ...base,
      id: "ent_0001",
      title: "Sky of Velmar",
      type: "place",
      status: "canon",
    },
    {
      ...base,
      id: "ent_0003",
      title: "Harbour Ward",
      type: "place",
      status: "canon",
    },
    {
      ...base,
      id: "ent_0004",
      title: "Ister",
      type: "character",
      status: "canon",
    },
  ] as unknown as Entry[];

  it("folds a type group from its heading, with the count shown, and opens it again", async () => {
    list = mixed;
    renderList();
    const places = await screen.findByRole("button", { name: "Places 2" });
    expect(places).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(places);
    expect(places).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Sky of Velmar")).toBeNull();
    expect(screen.getByText("Ister")).toBeInTheDocument(); // other groups stay open

    await userEvent.click(places);
    expect(screen.getByText("Sky of Velmar")).toBeInTheDocument();
  });

  it("shows search matches inside a folded group", async () => {
    list = mixed;
    renderList();
    await userEvent.click(
      await screen.findByRole("button", { name: "Places 2" }),
    );
    await userEvent.type(screen.getByLabelText("Search entries"), "harbour");
    expect(screen.getByText("Harbour Ward")).toBeInTheDocument();
  });
});
