import { describe, expect, it } from "vitest";
import { BADGE_CLASS, badgeOf, existingSecretOf, proposalSummary, proseSecretOf } from "@/lib/review";
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
    // The judge's values arrive as "<key>: <value>" (api/sagaloom/check/contradiction.py _to_flag).
    const hard = flag({
      fact_key: "Seats", existing_fact: "Council seats: Two of seven", new_fact: "Seats: Five", severity: "hard",
    });
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
    // A secret entry's keys are masked too (M2).
    expect(proposalSummary(secretDraft, check([added]), open)).toBe("a secret fact: Salt → a secret fact");
  });

  it("unmasks a secret draft key and value while the world shows secrets (R4)", () => {
    const secretFact: Proposal = {
      ...create,
      after: { ...create.after!, facts: [{ key: "Motto", value: "Tide", refs: [], status: "secret", told_by: null }] },
    };
    const added = flag({ kind: "retcon", fact_key: "Motto", existing_fact: "Salt", new_fact: "Tide" });
    expect(proposalSummary(secretFact, check([added]), open)).toBe("a secret fact: Salt → a secret fact");
    expect(proposalSummary(secretFact, check([added]), open, open, true)).toBe("Motto: Salt → Tide");
    const secretDraft: Proposal = { ...create, after: { ...create.after!, status: "secret" } };
    expect(proposalSummary(secretDraft, check([added]), open, open, true)).toBe("Motto: Salt → Tide");
  });

  it("strips the judge's key prefix but never a retcon's bare value", () => {
    const judged = flag({
      fact_key: "Moons", existing_fact: "Only light in the night sky: Ister", new_fact: "moons: Two", severity: "hard",
    });
    expect(proposalSummary(create, check([judged]), open)).toBe("Moons: Ister → Two");
    const colon = flag({ kind: "retcon", fact_key: "Motto", existing_fact: "Ward: keep", new_fact: "Tide: turn" });
    expect(proposalSummary(create, check([colon]), open)).toBe("Motto: Ward: keep → Tide: turn");
  });

  it("falls back to a keyless conflict's prose, then a keyed note's, masked like the card", () => {
    const prose = flag({
      entry_id: "ent_0012", severity: "hard", existing_quote: "the only light", new_quote: "three moons",
      explanation: "Ister is the only moon.",
    });
    expect(proposalSummary(create, check([prose]), open)).toBe("Ister is the only moon.");
    expect(proposalSummary(create, check([prose]), open, () => true)).toBe("Conflict with ent_0012");
    const possible = { ...prose, severity: "possible" as const };
    expect(proposalSummary(create, check([possible]), open, () => true)).toBe("Possible conflict with ent_0012");
    const belief = flag({
      kind: "note", severity: "note", entry_id: "ent_0004", fact_key: "Moons",
      existing_fact: "Moons: One", new_fact: "Moons: Three", explanation: "The Choir sings of three moons.",
    });
    expect(proposalSummary(create, check([belief]), open)).toBe("The Choir sings of three moons.");
    expect(proposalSummary(create, check([belief]), open, () => true)).toBe("Note with ent_0004");
    // A conflict outranks a note, as the badge does.
    expect(proposalSummary(create, check([belief, prose]), open)).toBe("Ister is the only moon.");
    // Through the shared rule: an entry holding a secret fact hides the prose.
    const ister = {
      id: "ent_0012", status: "canon",
      facts: [{ key: "Truth", value: "A lantern", refs: [], status: "secret", told_by: null }],
    } as unknown as Entry;
    expect(proposalSummary(create, check([prose]), existingSecretOf(create, [ister]), proseSecretOf(create, [ister]))).toBe(
      "Conflict with ent_0012",
    );
  });

  it("follows the badge precedence: the line explains the badge", () => {
    const prose = flag({ entry_id: "ent_0012", severity: "hard", explanation: "Ister is the only moon." });
    const dup = flag({ kind: "note", entry_id: "ent_0002", explanation: "Possible duplicate of ent_0002 'Harbour Council'" });
    const retcon = flag({ kind: "retcon", fact_key: "Seats", existing_fact: "Seven", new_fact: "Five" });
    expect(proposalSummary(create, check([dup, prose]), open)).toBe("Ister is the only moon.");
    expect(proposalSummary(create, check([retcon, prose]), open)).toBe("Ister is the only moon.");
    expect(proposalSummary(create, check([dup, retcon, prose]), open, () => true)).toBe("Conflict with ent_0012");
    // Hard before possible, keyed or not.
    const possibleKeyed = flag({
      fact_key: "Seats", existing_fact: "Seats: Seven", new_fact: "Seats: Five", severity: "possible",
    });
    expect(proposalSummary(create, check([possibleKeyed, prose]), open)).toBe("Ister is the only moon.");
    const possibleProse = { ...prose, severity: "possible" as const, explanation: "Maybe one moon." };
    expect(proposalSummary(create, check([possibleProse, possibleKeyed]), open)).toBe("Seats: Seven → Five");
    // A retcon still outranks a duplicate note.
    expect(proposalSummary(create, check([dup, retcon]), open)).toBe("Seats: Seven → Five");
  });

  it("masks a key whose every fact is secret, in the draft or before, or a secret entry's key", () => {
    const heir = (status: "canon" | "secret") => ({ key: "True heir", value: "Mira", refs: [], status, told_by: null });
    const retcon = flag({
      kind: "retcon", entry_id: "ent_0007", fact_key: "True heir", existing_fact: "Mira", new_fact: "Oren",
    });
    const before = {
      id: "ent_0007", world_id: "w1", title: "House Varr", type: "faction", body: "", status: "canon", aliases: [],
      links: [], facts: [heir("secret")], version: 1, created_at: "", updated_at: "",
    } as unknown as Entry;
    const update: Proposal = {
      ...create, action: "update", entry_id: "ent_0007", before,
      after: { ...create.after!, facts: [{ ...heir("canon"), value: "Oren" }] },
    };
    expect(proposalSummary(update, check([retcon]), existingSecretOf(update, []))).toBe(
      "a secret fact: a secret fact → Oren",
    );
    const drafted: Proposal = { ...create, after: { ...create.after!, facts: [heir("secret")] } };
    const added = flag({ kind: "retcon", fact_key: "true heir", existing_fact: null, new_fact: "Mira" });
    expect(proposalSummary(drafted, check([added]), open)).not.toMatch(/heir/i);
    const secretEntry: Proposal = { ...create, after: { ...create.after!, status: "secret" } };
    expect(proposalSummary(secretEntry, check([added]), open)).toBe("a secret fact: not set → a secret fact");
    // A key with canon facts on both sides stays readable.
    const open2: Proposal = { ...create, after: { ...create.after!, facts: [heir("canon")] } };
    expect(proposalSummary(open2, check([added]), open)).toBe("true heir: not set → Mira");
  });

  it("falls back to a duplicate note, a delete, then no conflicts", () => {
    const dup = flag({ kind: "note", entry_id: "ent_0002", title: "Harbour Council", explanation: "Possible duplicate of ent_0002 'Harbour Council'" });
    expect(proposalSummary(create, check([dup]), open)).toBe("Possible duplicate of ent_0002 'Harbour Council'");
    expect(proposalSummary(create, check([dup]), () => true)).toBe("Possible duplicate of ent_0002");
    const del: Proposal = { ...create, action: "delete", after: null };
    const refs = [{ id: "ent_0003", title: "Mayor", type: "character" as const }];
    expect(proposalSummary(del, check([], { dependents: refs }), open)).toBe("Deletes this entry · 1 entry mentions it");
    // A link-only dependent counts too: the number reveals no title.
    const linked = [...refs, { ...refs[0], id: "ent_0019", via: "link" as const }];
    expect(proposalSummary(del, check([], { dependents: linked }), open)).toBe("Deletes this entry · 2 entries mention it");
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

describe("proposalSummary secret fact", () => {
  it("says a secret fact changes when key, existing and proposed are all masked", () => {
    const secretCreate: Proposal = {
      ...create,
      after: { ...create.after!, status: "secret" },
    };
    const f = flag({ kind: "retcon", fact_key: "Seats", existing_fact: "Seven", new_fact: "Five" });
    expect(proposalSummary(secretCreate, check([f]), () => true)).toBe("A secret fact changes");
  });

  it("keeps the arrow form when only part is masked", () => {
    const f = flag({ kind: "retcon", fact_key: "Seats", existing_fact: "Seven", new_fact: "Five" });
    expect(proposalSummary(create, check([f]), () => true)).toBe("Seats: a secret fact → Five");
  });
});

describe("BADGE_CLASS", () => {
  it("fills the failed badge from the failed token", () => {
    expect(BADGE_CLASS.failed).toBe("bg-failed text-background");
  });
});
