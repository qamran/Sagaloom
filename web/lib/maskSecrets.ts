import type { LlmResponse } from "@/lib/types";

/** What a masked prompt line shows in the Under the hood drawer (R20.3). */
export const MASKED_LINE = "[secret fact hidden]";

// The block's wrapper tags, as regex sources: the one place both patterns below are built from.
const OPEN_TAG = String.raw`<untrusted_data[^>]*>`;
const CLOSE_TAG = String.raw`<\/untrusted_data>`;

/** An `<untrusted_data …>…</untrusted_data>` block, as one capture group (so `split` keeps it). */
export const UNTRUSTED = new RegExp(String.raw`(${OPEN_TAG}[\s\S]*?${CLOSE_TAG})`, "g");
const BLOCK_PARTS = new RegExp(String.raw`^(${OPEN_TAG})([\s\S]*)(${CLOSE_TAG})$`);

// Secret fact lines end `[secret]` or carry it before `(told by …)`; Pass 1 lines name their entry's status.
const SECRET_LINE = /\[secret\]|\(entry status: secret\)/;
const SECRET_ENTRY = /^Entry status: secret$/;
// A secret status anywhere in structured (JSON) output.
const SECRET_STATUS_JSON = /"status"\s*:\s*"secret"/;

function maskBlock(block: string): { text: string; masked: number } {
  const [, open, inner, close] = BLOCK_PARTS.exec(block) ?? ["", "", block, ""];
  let masked = 0;
  let secretEntry = false;
  const lines = inner.split("\n").map((line) => {
    if (secretEntry ? line.trim() !== "" : SECRET_LINE.test(line)) {
      masked += 1;
      return MASKED_LINE;
    }
    if (SECRET_ENTRY.test(line.trim())) secretEntry = true;
    return line;
  });
  return { text: open + lines.join("\n") + close, masked };
}

/**
 * Masks secrets in a prompt for display, inside untrusted blocks only (where canon is rendered by
 * `_build_prompt`). A line marked `[secret]` or `(entry status: secret)` is hidden; in a block with
 * the line `Entry status: secret`, every non-empty line after it is hidden too, so a secret entry
 * keeps only its Title, Type and status. Text outside the blocks is never changed.
 * The format is pinned by api/tests/check/test_prompt_fixture.py.
 */
export function maskPrompt(text: string): { text: string; masked: number } {
  let masked = 0;
  const out = text.replace(UNTRUSTED, (block: string) => {
    const r = maskBlock(block);
    masked += r.masked;
    return r.text;
  });
  return { text: out, masked };
}

const isSecret = (v: unknown) =>
  !!v && typeof v === "object" && (v as { status?: unknown }).status === "secret";

/** Args as an object: a string is parsed as JSON first (an unparsable one is not an object). */
function argsObject(args: unknown): unknown {
  if (typeof args !== "string") return args;
  try {
    return JSON.parse(args);
  } catch {
    return null;
  }
}

/**
 * True when tool-call args propose a secret: `status: "secret"` on the entry or on any fact. String
 * args (a provider's raw JSON) are parsed first; a string that is not JSON holds no secret status.
 * The args-shaped twin of `draftHoldsSecret` (lib/review.ts), which reads a Proposal instead.
 */
export function argsHoldSecret(raw: unknown): boolean {
  const args = argsObject(raw);
  if (!args || typeof args !== "object") return false;
  const facts = (args as { facts?: unknown }).facts;
  return isSecret(args) || (Array.isArray(facts) && facts.some(isSecret));
}

/** True when a model's reply carries a secret status: in a tool call's args, or in structured
 * (JSON) content such as a structured-output call's reply. */
export function responseHoldsSecret(r: LlmResponse | null): boolean {
  if (!r) return false;
  return SECRET_STATUS_JSON.test(r.content ?? "") || r.tool_calls.some((c) => argsHoldSecret(c.args));
}
