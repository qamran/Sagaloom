/** What a masked prompt line shows in the Under the hood drawer (R20.3). */
export const MASKED_LINE = "[secret fact hidden]";

/** An `<untrusted_data …>…</untrusted_data>` block: opening tag, content, closing tag. */
export const UNTRUSTED_BLOCK = /(<untrusted_data[^>]*>)([\s\S]*?)(<\/untrusted_data>)/g;

// Secret fact lines end `[secret]` or carry it before `(told by …)`; Pass 1 lines name their entry's status.
const SECRET_LINE = /\[secret\]|\(entry status: secret\)/;
const SECRET_ENTRY = /^Entry status: secret$/;

/**
 * Masks secrets in a prompt for display, inside untrusted blocks only (where canon is rendered by
 * `_build_prompt`). A line marked `[secret]` or `(entry status: secret)` is hidden; in a block with
 * the line `Entry status: secret`, every non-empty line after it is hidden too, so a secret entry
 * keeps only its Title, Type and status. Text outside the blocks is never changed.
 * The format is pinned by api/tests/check/test_prompt_fixture.py.
 */
export function maskPrompt(text: string): { text: string; masked: number } {
  let masked = 0;
  const out = text.replace(UNTRUSTED_BLOCK, (_m, open: string, inner: string, close: string) => {
    let secretEntry = false;
    const lines = inner.split("\n").map((line) => {
      if (secretEntry ? line.trim() !== "" : SECRET_LINE.test(line)) {
        masked += 1;
        return MASKED_LINE;
      }
      if (SECRET_ENTRY.test(line.trim())) secretEntry = true;
      return line;
    });
    return open + lines.join("\n") + close;
  });
  return { text: out, masked };
}
