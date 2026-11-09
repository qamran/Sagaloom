import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { MASKED_LINE, argsHoldSecret, maskPrompt, responseHoldsSecret } from "@/lib/maskSecrets";

// Real `_build_prompt` output, pinned by api/tests/check/test_prompt_fixture.py.
const fixture = readFileSync(join(__dirname, "fixtures", "judge-prompt.txt"), "utf-8").replace(/\r\n/g, "\n");

const block = (inner: string, source = "ent_0001") => `<untrusted_data source="${source}">\n${inner}\n</untrusted_data>`;

describe("maskPrompt on the real judge prompt", () => {
  const { text, masked } = maskPrompt(fixture);

  it("hides the Mayor's secret fact everywhere it appears", () => {
    expect(text).not.toContain("Yes, at every full Ister");
    expect(text).not.toContain("Sings with the Ashen Choir");
    expect(text).toContain(MASKED_LINE);
    expect(masked).toBeGreaterThan(0);
  });

  it("hides the told-by secret fact and the Pass 1 pair line from the secret entry", () => {
    expect(fixture).toContain("[secret] (told by Ilsa Corran)");
    expect(text).not.toContain("(told by Ilsa Corran)");
    expect(fixture).toContain("(entry status: secret)");
    expect(text).not.toContain("(entry status: secret)");
    // The author's own side of that pair stays.
    expect(text).toContain("Proposed: Kept in: A drawer in the Tidehall [canon]");
    expect(text).toContain("## Pairs with entry ent_0019");
  });

  it("hides the body and facts of the secret entry, keeping its title, type and status", () => {
    expect(text).toContain("Title: The Choir Ledger");
    expect(text).toContain("Type: item");
    expect(text).toContain("Entry status: secret");
    expect(text).not.toContain("Ilsa Corran's crypt");
    expect(text).not.toContain("cipher of moon phases");
    expect(text).not.toContain("Every member of the Ashen Choir");
  });

  it("leaves non-secret lines and the text outside the blocks as they were", () => {
    expect(text).toContain("- Age: 54 [canon]");
    expect(text).toContain("Existing: Age: 54 [canon] (entry status: canon)");
    expect(text).toContain("The Harbour Council runs Velmar.");
    expect(text).toContain("# Pass 1: candidate fact pairs (same key)");
    expect(text).toContain("## Entry ent_0019");
    // Every block keeps its wrapper, so the drawer still sets it apart.
    expect(text.match(/<untrusted_data /g)).toHaveLength(fixture.match(/<untrusted_data /g)!.length);
    expect(text.match(/<\/untrusted_data>/g)).toHaveLength(fixture.match(/<\/untrusted_data>/g)!.length);
  });
});

describe("maskPrompt", () => {
  it("masks a secret fact line with told-by after the marker", () => {
    const { text, masked } = maskPrompt(block("- Key: v [secret] (told by Ilsa)\n- Other: w [canon]"));
    expect(text).toBe(block(`${MASKED_LINE}\n- Other: w [canon]`));
    expect(masked).toBe(1);
  });

  it("masks a Pass 1 line from a secret entry", () => {
    const line = "Existing: Kept in: The crypt [canon] (entry status: secret)";
    const { text, masked } = maskPrompt(block(`Proposed: Kept in: The quay [canon]\n${line}`));
    expect(text).not.toContain("The crypt");
    expect(text).toContain("Proposed: Kept in: The quay [canon]");
    expect(masked).toBe(1);
  });

  it("never masks [secret] outside an untrusted block", () => {
    const outside = "Facts marked [secret] are hidden.";
    expect(maskPrompt(outside)).toEqual({ text: outside, masked: 0 });
    const { text } = maskPrompt(`${outside}\n${block("- A: b [canon]")}`);
    expect(text).toContain(outside);
  });

  it("masks a single-line block's content but keeps its tags", () => {
    const { text, masked } = maskPrompt('<untrusted_data source="x">Lore [secret]</untrusted_data>');
    expect(text).toBe(`<untrusted_data source="x">${MASKED_LINE}</untrusted_data>`);
    expect(masked).toBe(1);
  });

  it("starts each block fresh: a secret entry does not mask the next block", () => {
    const secret = block("Title: Ledger\nType: item\nEntry status: secret\nBody:\nHidden lore", "ent_0019");
    const open = block("Title: Quay\nEntry status: canon\nBody:\nOpen lore", "ent_0006");
    const { text } = maskPrompt(`${secret}\n${open}`);
    expect(text).not.toContain("Hidden lore");
    expect(text).toContain("Open lore");
  });
});

describe("argsHoldSecret", () => {
  it("is true for a secret entry or any secret fact in tool args", () => {
    expect(argsHoldSecret({ action: "create", title: "Ledger", status: "secret" })).toBe(true);
    expect(
      argsHoldSecret({ action: "update", facts: [{ key: "Age", value: "60" }, { key: "Sings", value: "Yes", status: "secret" }] }),
    ).toBe(true);
  });

  it("is false for canon args and for anything that is not an object", () => {
    expect(argsHoldSecret({ action: "create", title: "Quay", status: "canon", facts: [{ key: "A", value: "b" }] })).toBe(false);
    expect(argsHoldSecret({ query: "secret" })).toBe(false);
    expect(argsHoldSecret(null)).toBe(false);
    expect(argsHoldSecret("status: secret")).toBe(false);
    expect(argsHoldSecret({ facts: "x" })).toBe(false);
  });
});

describe("responseHoldsSecret", () => {
  const base = { tool_calls: [], prompt_tokens: 0, completion_tokens: 0, cost_usd: 0, latency_ms: 0 };

  it("is true for structured content (the extractor's JSON) that holds a secret status", () => {
    const content = JSON.stringify({
      candidates: [{ title: "Ledger", type: "item", facts: [{ key: "Kept in", value: "Crypt", status: "secret" }], excerpt: "x" }],
    });
    expect(responseHoldsSecret({ ...base, content })).toBe(true);
  });

  it("is true for a response tool call with secret args", () => {
    const call = { id: null, name: "create_or_update_entry", args: { action: "create", status: "secret" } };
    expect(responseHoldsSecret({ ...base, content: "", tool_calls: [call] })).toBe(true);
  });

  it("is false for the extractor's real output, which has no status, and for plain text", () => {
    const content = JSON.stringify({
      candidates: [{ title: "Quay", type: "place", aliases: [], facts: [{ key: "Lamps", value: "Iron" }], excerpt: "x" }],
    });
    expect(responseHoldsSecret({ ...base, content })).toBe(false);
    expect(responseHoldsSecret({ ...base, content: "The status is secret." })).toBe(false);
    expect(responseHoldsSecret(null)).toBe(false);
  });
});
