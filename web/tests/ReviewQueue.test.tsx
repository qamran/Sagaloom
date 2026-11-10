import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewQueue } from "@/components/ReviewQueue";
import { SecretsWorldProvider, SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { CheckResult, Entry, Flag, PendingInterrupt, Proposal, Status } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

const flag: Flag = {
  kind: "conflict", entry_id: "ent_0012", title: "Ister", fact_key: "Moons", existing_fact: "Moons: one",
  new_fact: "Moons: three", existing_quote: null, new_quote: null, severity: "hard", explanation: "Moons differ.",
  suggested_fix: null, existing_secret: true,
};
const proposal = (id: string, title: string, status: Status): Proposal => ({
  proposal_id: id, action: "create", world_id: "w1", entry_id: null, before: null,
  after: { title, type: "place", body: "", status, aliases: [], facts: [] },
});
const check = (id: string, flags: Flag[] = []): CheckResult => ({
  proposal_id: id, verdict: flags.length ? "conflict" : "none", flags, dependents: [],
});
const pending: PendingInterrupt = {
  proposals: [proposal("p_a", "Sky of Velmar", "canon"), proposal("p_b", "The Choir Ledger", "secret")],
  checks: { p_a: check("p_a", [flag]), p_b: check("p_b") },
};
const ister = { id: "ent_0012", title: "Ister", type: "place", status: "canon", facts: [] } as unknown as Entry;

const ui = () => (
  <SecretsWorldProvider worldId="w1">
    <ReviewQueue pending={pending} canon={[ister]} selectedId="p_a" chosen={{}} onSelect={vi.fn()} />
  </SecretsWorldProvider>
);

describe("ReviewQueue", () => {
  it("queue summary unmasks while the world shows secrets", () => {
    const { unmount } = render(ui());
    expect(screen.getByText("Moons: a secret fact → three")).toBeInTheDocument();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(ui());
    expect(screen.getByText("Moons: one → three")).toBeInTheDocument();
  });

  it("queue title follows the world toggle", () => {
    const { unmount } = render(ui());
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(ui());
    expect(screen.getByText("The Choir Ledger")).toBeInTheDocument();
    expect(screen.queryByText("Secret entry")).toBeNull();
  });

  it("queue summary unmasks a secret draft fact while the world shows secrets", () => {
    const motto: Proposal = {
      ...proposal("p_c", "Tide Council", "canon"),
      after: {
        title: "Tide Council", type: "faction", body: "", status: "canon", aliases: [],
        facts: [{ key: "Motto", value: "Tide", refs: [], status: "secret", told_by: null }],
      },
    };
    const retcon: Flag = { ...flag, kind: "retcon", severity: null, entry_id: "", fact_key: "Motto", existing_fact: "Salt", new_fact: "Tide", existing_secret: false };
    const one: PendingInterrupt = { proposals: [motto], checks: { p_c: check("p_c", [retcon]) } };
    const view = () => (
      <SecretsWorldProvider worldId="w1">
        <ReviewQueue pending={one} canon={[ister]} selectedId="p_c" chosen={{}} onSelect={vi.fn()} />
      </SecretsWorldProvider>
    );
    const { unmount } = render(view());
    expect(screen.getByText("a secret fact: Salt → a secret fact")).toBeInTheDocument();
    expect(screen.queryByText(/Tide$/)).toBeNull();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(view());
    expect(screen.getByText("Motto: Salt → Tide")).toBeInTheDocument();
  });

  it("hides the title of an entry stored as secret after its proposal was drafted", () => {
    const drafted = { id: "ent_0019", title: "The Choir Ledger", type: "item", status: "canon", facts: [] } as unknown as Entry;
    const update: Proposal = {
      proposal_id: "p_u", action: "update", world_id: "w1", entry_id: "ent_0019", before: drafted,
      after: { title: "The Choir Ledger", type: "item", body: "", status: "canon", aliases: [], facts: [] },
    };
    const one: PendingInterrupt = { proposals: [update], checks: { p_u: check("p_u") } };
    const view = () => (
      <SecretsWorldProvider worldId="w1">
        <ReviewQueue pending={one} canon={[{ ...drafted, status: "secret" }]} selectedId="p_u" chosen={{}} onSelect={vi.fn()} />
      </SecretsWorldProvider>
    );
    const { unmount } = render(view());
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    unmount();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(view());
    expect(screen.getByText("The Choir Ledger")).toBeInTheDocument();
  });

  it("follows the provider's world, not the active one", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(
      <SecretsWorldProvider worldId="w2">
        <ReviewQueue pending={pending} canon={[ister]} selectedId="p_a" chosen={{}} onSelect={vi.fn()} />
      </SecretsWorldProvider>,
    );
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
  });
});
