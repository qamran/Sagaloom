import { describe, expect, it } from "vitest";
import { badgeOf, existingSecretOf, proposalSummary, proseSecretOf } from "@/lib/review";
import type { CheckResult, Entry, Flag, Proposal } from "@/lib/types";

const flag = (over: Partial<Flag>): Flag => ({
  kind: "conflict", entry_id: "ent_0011", title: "The Salt Guild", fact_key: null, existing_fact: null,
  new_fact: null, existing_quote: null, new_quote: null, severity: null, explanation: "",
  suggested_fix: null, existing_secret: false, ...over,
});
const check = (flags: Flag[], over: Partial<CheckResult> = {}): CheckResult => ({
  proposal_id: "p_1", verdict: "none", flags, dependents: [], ...over,
});
const create: Proposal = {
  proposal_id: "p_1", action: "create", world_id: "w1", entry_id: null, before: null,
  after: { title: "Tide Council", type: "faction", body: "", status: "canon", aliases: [], facts: [] },
};

describe("badgeOf", () => {
  it("prefers the server's badge", () => {
    expect(badgeOf(check([], { badge: "retcon" }))).toBe("retcon");
  });

  it("falls back to the server's precedence", () => {
    const hard = flag({ severity: "hard" });
    const possible = flag({ severity: "possible" });
    const retcon = flag({ kind: "retcon" });
    const note = flag({ kind: "note" });
    expect(badgeOf(check([hard], { verdict: "failed" }))).toBe("failed");
    expect(badgeOf(check([note, retcon, possible, hard]))).toBe("conflict");
    expect(badgeOf(check([note, retcon, possible]))).toBe("possible");
    expect(badgeOf(check([note, retcon]))).toBe("retcon");
    expect(badgeOf(check([note]))).toBe("note");
    // The verdict alone never raises a conflict badge, as on the server.
    expect(badgeOf(check([], { verdict: "possible" }))).toBe("clear");
  });
});

describe("proposalSummary", () => {
  const open = () => false;

  it("names the first conflicting fact, masking a secret value", () => {
    const retcon = flag({ kind: "retcon", fact_key: "Seats", existing_fact: "Seven", new_fact: "Five" });
    const hard = flag({ fact_key: "Seats", existing_fact: "Two of seven", new_fact: "Five", severity: "hard" });
    expect(proposalSummary(create, check([retcon, hard]), open)).toBe("Seats: Two of seven → Five");
    expect(proposalSummary(create, check([retcon]), open)).toBe("Seats: Seven → Five");
    expect(proposalSummary(create, check([{ ...retcon, new_fact: null }]), () => true)).toBe(
      "Seats: a secret fact → removed",
    );
  });

  it("masks the new side when the key holds a secret proposed value among canon ones", () => {
    const mixed: Proposal = {
      ...create,
      action: "update",
      after: {
        ...create.after!,
        facts: [
          { key: "Members", value: "Several hundred", refs: [], status: "canon", told_by: null },
          { key: "members", value: "Lantern-bearers", refs: [], status: "secret", told_by: null },
        ],
      },
    };
    const retcon = flag({
      kind: "retcon", fact_key: "Members", existing_fact: "About sixty", new_fact: "Several hundred, Lantern-bearers",
    });
    const line = proposalSummary(mixed, check([retcon]), open);
    expect(line).toBe("Members: About sixty → a secret fact");
    expect(line).not.toMatch(/Lantern-bearers/);
    const secretDraft: Proposal = { ...create, after: { ...create.after!, status: "secret" } };
    const added = flag({ kind: "retcon", fact_key: "Motto", existing_fact: "Salt", new_fact: "Tide" });
    expect(proposalSummary(secretDraft, check([added]), open)).toBe("Motto: Salt → a secret fact");
  });

  it("falls back to a duplicate note, a delete, then no conflicts", () => {
    const dup = flag({ kind: "note", entry_id: "ent_0002", title: "Harbour Council", explanation: "Possible duplicate of ent_0002 'Harbour Council'" });
    expect(proposalSummary(create, check([dup]), open)).toBe("Possible duplicate of ent_0002 'Harbour Council'");
    expect(proposalSummary(create, check([dup]), () => true)).toBe("Possible duplicate of ent_0002");
    const del: Proposal = { ...create, action: "delete", after: null };
    const refs = [{ id: "ent_0003", title: "Mayor", type: "character" as const }];
    expect(proposalSummary(del, check([], { dependents: refs }), open)).toBe("Deletes this entry · 1 entry mentions it");
    expect(proposalSummary(del, check([], { dependents: [...refs, ...refs] }), open)).toBe(
      "Deletes this entry · 2 entries mention it",
    );
    expect(proposalSummary(create, check([]), open)).toBe("No conflicts found");
  });
});

describe("existingSecretOf", () => {
  const cited = flag({ entry_id: "ent_0012", fact_key: "Members", existing_fact: "Ashen Choir" });
  const entry = (status: "canon" | "secret") =>
    ({
      id: "ent_0012", status,
      facts: [{ key: "Members", value: "Ashen Choir", refs: [], status, told_by: null }],
    }) as unknown as Entry;

  it("fails closed for another entry until canon has loaded", () => {
    expect(existingSecretOf(create, undefined)(cited)).toBe(true);
    expect(existingSecretOf(create, [])(cited)).toBe(false);
  });

  it("does not fail closed for the proposal's own entry", () => {
    expect(existingSecretOf({ ...create, entry_id: "ent_0012" }, undefined)(cited)).toBe(false);
  });

  it("trusts the server's mark and a secret fact in canon", () => {
    expect(existingSecretOf(create, [])(flag({ existing_secret: true }))).toBe(true);
    expect(existingSecretOf(create, [entry("secret")])(cited)).toBe(true);
    expect(existingSecretOf(create, [entry("canon")])(cited)).toBe(false);
  });
});

describe("proseSecretOf", () => {
  const dup = flag({ kind: "note", entry_id: "ent_0012", fact_key: null, explanation: "Possible duplicate of ent_0012 'The Salt Guild'" });
  const entryWithSecretFact = {
    id: "ent_0012", status: "canon",
    facts: [{ key: "Members", value: "x", refs: [], status: "secret", told_by: null }],
  } as unknown as Entry;

  it("hides a keyless note about a non-secret entry that holds a secret fact", () => {
    const secret = proseSecretOf(create, [entryWithSecretFact]);
    expect(proposalSummary(create, check([dup]), existingSecretOf(create, [entryWithSecretFact]), secret)).toBe(
      "Possible duplicate of ent_0012",
    );
  });

  it("hides it when the draft holds a secret fact", () => {
    const draft: Proposal = {
      ...create,
      after: { ...create.after!, facts: [{ key: "k", value: "v", refs: [], status: "secret", told_by: null }] },
    };
    expect(proseSecretOf(draft, [])(dup)).toBe(true);
    expect(proseSecretOf(create, [])(dup)).toBe(false);
  });
});
