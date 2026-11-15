/** How to try each agent tool from Studio → Tools: what the tool does in one line, a message to
 * send in Chat, and what it should show. The examples use the sample world Velmar (the README
 * walkthroughs use the same ones). */
export interface ToolTest {
  /** What the tool does, in one plain line (the agent's own description is longer). */
  summary: string;
  /** The message to send in Chat. */
  prompt: string;
  /** What the author should see. */
  expect: string;
}

export const TOOL_TESTS: Record<string, ToolTest> = {
  search_canon: {
    summary: "Finds entries by meaning, so answers cite your canon.",
    prompt: "How many moons does Velmar have?",
    expect: "An answer that cites entry ids, such as ent_0012.",
  },
  create_or_update_entry: {
    summary: "Drafts a new or changed entry for your approval. It never writes canon itself.",
    prompt: "Captain Sorn is the harbourmaster of Lantern Quay.",
    expect: "An approval card. Nothing is saved until you approve it.",
  },
  check_contradiction: {
    summary: "Checks a what-if claim against canon without proposing anything.",
    prompt: "Without changing anything, would it contradict canon if Velmar had three moons?",
    expect: "An answer naming the clashing entry, and no approval card.",
  },
  export_world: {
    summary: "Gives you a Markdown zip of the world to download.",
    prompt: "Export the world, leaving out secrets.",
    expect: "A download link for a Markdown zip of the world.",
  },
  real_world_reference: {
    summary: "Looks up real-world history on Wikipedia, for inspiration only.",
    prompt: "What did Byzantine trade routes look like?",
    expect: "An answer with Wikipedia links, marked as reference, not canon.",
  },
  remember_preference: {
    summary: "Saves a preference you state (tone, genre, a banned trope) for this world.",
    prompt: "Remember: keep the tone grim.",
    expect: "A Remembered chip with Undo. Studio → Memory lists it.",
  },
  import_wiki: {
    summary: "Turns Wikipedia or Fandom pages into proposals you review.",
    prompt: "Import this page: https://en.wikipedia.org/wiki/Rivendell",
    expect: "An approval card for Rivendell with its source and licence. Best tried in a new world.",
  },
};

export const chatHref = (prompt: string) => `/chat?prompt=${encodeURIComponent(prompt)}`;
