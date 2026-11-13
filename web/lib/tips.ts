// "Useful tips" shown once per browser session after sign-in, in random order, until the author ticks
// "Don't show this again". Both flags live in this browser only: the opt-out per account in localStorage
// (`sagaloom.tips.<userId>.hidden`), the "already shown this session" flag in sessionStorage.

export const TIPS: readonly string[] = [
  "Nothing enters canon until you approve it: every change waits on a review card.",
  "State a fact as a plain sentence, such as \"Velmar has three moons\", and the agent drafts a proposal for you to review.",
  "Ask a question and the answer cites entry IDs like ent_0012, or says \"not in canon\" when your world has no answer.",
  "Brainstormed ideas are labelled as suggestions. They never change canon until you state one as fact.",
  "A Conflict badge quotes both sides, so you can see exactly which entry clashes and why.",
  "Save as myth keeps a clashing fact as an in-world story instead of overwriting canon. You can say who tells it.",
  "Myths and rumours never raise false contradiction alarms.",
  "A Retcon badge warns you when a change rewrites an established fact.",
  "A Note badge flags a new entry that looks like a duplicate of one you already have.",
  "Use Edit on a review card to change a proposal before it enters canon.",
  "The Review page collects every pending proposal across your chats, so you can decide them in one batch.",
  "On Review, \"Approve all with no issues\" clears every clean proposal in one click.",
  "Refresh the page while a review card is pending: it will still be there.",
  "Import turns pasted notes or a .md or .txt file into proposals, and stores your own words verbatim.",
  "Import → Fan wiki turns Wikipedia or Fandom pages into proposals, with each wiki's licence recorded.",
  "Type @ in the chat box to mention an entry by name.",
  "Say \"Remember: keep the tone grim\" and the agent keeps that preference in every new chat in this world.",
  "Studio → Memory lists everything the agent remembers about your world.",
  "Ask about the real world, such as \"What did Byzantine trade routes look like?\", and the agent can look it up on Wikipedia.",
  "Open Under the hood on any reply to see every prompt sent, the tools the agent called and what it cost.",
  "The line under each reply shows its tokens and cost, step by step.",
  "Your monthly AI budget and this month's spend are shown in the header.",
  "Show secrets in the header reveals hidden facts. Leave it off when you share your screen.",
  "Create another world from the world picker → + New world. Each world has its own canon, chats and memory.",
  "Canon → Download as Markdown exports your world as a zip that opens in Obsidian.",
  "Compare shows how Sagaloom's features line up with other world-building tools.",
  "Studio → Feature map has Try it links that fill the chat box with a demo prompt.",
];

const hiddenKey = (userId: string) => `sagaloom.tips.${userId}.hidden`;
export const TIPS_SESSION_KEY = "sagaloom.tips.shown";

/** True when this account ticked "Don't show this again" in this browser. */
export function tipsHidden(userId: string): boolean {
  try {
    return localStorage.getItem(hiddenKey(userId)) === "1";
  } catch {
    return false;
  }
}

export function setTipsHidden(userId: string, hidden: boolean): void {
  try {
    if (hidden) localStorage.setItem(hiddenKey(userId), "1");
    else localStorage.removeItem(hiddenKey(userId));
  } catch {
    /* storage unavailable: the tips come back next session */
  }
}

/** True once the tips were shown in this browser session, so they appear at startup, not on every page. */
export function tipsShownThisSession(): boolean {
  try {
    return sessionStorage.getItem(TIPS_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markTipsShown(): void {
  try {
    sessionStorage.setItem(TIPS_SESSION_KEY, "1");
  } catch {
    /* storage unavailable: at worst the tips show again on a full reload */
  }
}

/** A shuffled copy (Fisher-Yates); `random` is injectable for tests. */
export function shuffled<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
