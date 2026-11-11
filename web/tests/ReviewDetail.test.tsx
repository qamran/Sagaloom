import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewDetail } from "@/components/ReviewDetail";
import type { AgentStream } from "@/lib/useAgentStream";
import { getEntries } from "@/lib/api";
import type { CheckResult, Entry, Decision, Flag, PendingInterrupt, Proposal } from "@/lib/types";

vi.mock("@/lib/world", () => ({
  useWorld: () => ({ world: { id: "w1", name: "Velmar" }, isLoading: false, error: null }),
}));
vi.mock("@/lib/api", () => ({ getEntries: vi.fn(async () => []) }));

let stream: AgentStream;
vi.mock("@/lib/useAgentStream", () => ({ useAgentStream: () => stream }));

const proposal = (id: string, title: string, action: Proposal["action"] = "create"): Proposal => ({
  proposal_id: id, action, world_id: "w1", entry_id: action === "create" ? null : "ent_0007",
  before: null,
  after: action === "delete" ? null : { title, type: "place", body: "", status: "canon", aliases: [], facts: [] },
});
const conflictFlag: Flag = {
  kind: "conflict", entry_id: "ent_0012", title: "Ister", fact_key: "Moons", existing_fact: "Moons: one",
  new_fact: "Moons: three", existing_quote: null, new_quote: null, severity: "hard", explanation: "Moons differ.",
  suggested_fix: null, existing_secret: false,
};
const clean = (id: string): CheckResult => ({ proposal_id: id, verdict: "none", flags: [], dependents: [], badge: "clear" });
const conflict = (id: string): CheckResult => ({
  proposal_id: id, verdict: "conflict", flags: [conflictFlag], dependents: [], badge: "conflict",
});
const pendingOf = (...rows: [Proposal, CheckResult][]): PendingInterrupt => ({
  proposals: rows.map(([p]) => p),
  checks: Object.fromEntries(rows.map(([p, c]) => [p.proposal_id, c])),
});
const two = pendingOf(
  [proposal("p_a", "Tide Council"), clean("p_a")],
  [proposal("p_b", "Sky of Velmar", "update"), conflict("p_b")],
);

const base = (over: Partial<AgentStream> = {}): AgentStream => ({
  messages: [], streaming: false, pending: null, usage: null, turns: [], status: "idle", error: null, loaded: true,
  worldId: "w1", kind: "chat", title: null, importNote: null, chosen: {}, sent: null, turnEvents: [],
  send: vi.fn(), decide: vi.fn(async () => undefined), choose: vi.fn(async () => undefined),
  chooseMany: vi.fn(async () => undefined), unchoose: vi.fn(), ...over,
});

const ui = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ReviewDetail threadId="t1" />
  </QueryClientProvider>
);

beforeEach(() => {
  vi.mocked(getEntries).mockReset().mockResolvedValue([]);
  stream = base({ pending: two });
});

describe("ReviewDetail", () => {
  it("lists the queue with the lead line and selects the first card", async () => {
    render(ui());
    expect(screen.getByText("2 proposals · nothing enters canon until you decide")).toBeInTheDocument();
    const queue = screen.getByRole("complementary", { name: "Pending proposals" });
    // Fails closed: until this world's canon has loaded, the update's own entry (it may be stored
    // secret) and the cited entry's value stay hidden.
    expect(within(queue).getByText("Secret entry")).toBeInTheDocument();
    expect(within(queue).queryByText("Sky of Velmar")).toBeNull();
    expect(within(queue).queryByText("Moons: one → three")).toBeNull();
    expect(await within(queue).findByText("Moons: one → three")).toBeInTheDocument();
    const rows = within(queue).getAllByRole("button", { name: /Tide Council|Sky of Velmar/ });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("aria-current", "true");
    expect(rows[1]).not.toHaveAttribute("aria-current");
    expect(within(rows[1]).getByText("Moons: one → three")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Review proposal: Tide Council" })).toBeInTheDocument();
  });

  it("selects another proposal from the queue", async () => {
    render(ui());
    await userEvent.click(await screen.findByRole("button", { name: /Sky of Velmar/ }));
    expect(screen.getByRole("region", { name: "Review proposal: Sky of Velmar" })).toBeInTheDocument();
  });

  it("Approve 1 with no issues approves only the clean proposal", async () => {
    render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Approve 1 with no issues" }));
    expect(stream.chooseMany).toHaveBeenCalledWith([{ proposal_id: "p_a", action: "approve" }]);
  });

  it("leaves out a clean delete and a proposal that is already chosen", async () => {
    const del = proposal("p_d", "Gone", "delete");
    stream = base({
      pending: pendingOf(
        [del, clean("p_d")],
        [proposal("p_c", "Done"), clean("p_c")],
        [proposal("p_e", "Ok"), clean("p_e")],
      ),
      chosen: { p_c: { proposal_id: "p_c", action: "reject" } },
    });
    render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Approve 1 with no issues" }));
    expect(stream.chooseMany).toHaveBeenCalledWith([{ proposal_id: "p_e", action: "approve" }]);
  });

  it("hides the approve button when no proposal is clean", () => {
    stream = base({ pending: pendingOf([proposal("p_b", "Sky of Velmar", "update"), conflict("p_b")]) });
    render(ui());
    expect(screen.queryByRole("button", { name: /with no issues/ })).toBeNull();
  });

  it("Reject all rejects every proposal", async () => {
    render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Reject all" }));
    expect(stream.chooseMany).toHaveBeenCalledWith([
      { proposal_id: "p_a", action: "reject" },
      { proposal_id: "p_b", action: "reject" },
    ]);
  });

  it("Submit 2 decisions is disabled until both are chosen, then decides", async () => {
    const { unmount } = render(ui());
    expect(screen.getByRole("button", { name: "Submit 2 decisions" })).toBeDisabled();
    unmount();
    stream = base({ pending: two, chosen: { p_a: { proposal_id: "p_a", action: "approve" } } });
    const half = render(ui());
    expect(screen.getByRole("button", { name: "Submit 2 decisions" })).toBeDisabled();
    half.unmount();
    const chosen: Record<string, Decision> = {
      p_a: { proposal_id: "p_a", action: "approve" },
      p_b: { proposal_id: "p_b", action: "reject" },
    };
    stream = base({ pending: two, chosen });
    render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Submit 2 decisions" }));
    expect(stream.decide).toHaveBeenCalledWith([chosen.p_a, chosen.p_b]);
  });

  it("disables the cards and says so while sending", () => {
    stream = base({ pending: two, streaming: true, status: "streaming" });
    render(ui());
    expect(screen.getByText("Sending your decisions…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  });

  it("keeps the cards, disabled, while the hook has cleared pending to send", () => {
    const { rerender } = render(ui());
    stream = base({ pending: null, sent: { pending: two, chosen: {} }, streaming: true, status: "streaming" });
    rerender(ui());
    expect(screen.getByText("Sending your decisions…")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Review proposal: Tide Council" })).toBeInTheDocument();
  });

  it("shows the re-asked card after a myth decision", async () => {
    const one = pendingOf([proposal("p_a", "Tide Council"), conflict("p_a")]);
    stream = base({ pending: one, chosen: { p_a: { proposal_id: "p_a", action: "save_as_myth" } } });
    const { rerender } = render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Submit 1 decision" }));
    expect(stream.decide).toHaveBeenCalled();
    // The turn ends with a new interrupt on the same thread.
    stream = base({ pending: pendingOf([proposal("p_a2", "Tide Council myth"), clean("p_a2")]) });
    rerender(ui());
    expect(screen.getByRole("region", { name: "Review proposal: Tide Council myth" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open in Chat" })).toBeNull();
  });

  it("lists the review notes and both links once the turn is done", async () => {
    stream = base({
      pending: pendingOf([proposal("p_a", "Tide Council"), clean("p_a")]),
      chosen: { p_a: { proposal_id: "p_a", action: "approve" } },
      messages: [{ role: "review", content: "Old note." }],
    });
    const { rerender } = render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Submit 1 decision" }));
    stream = base({
      pending: null,
      messages: [
        { role: "review", content: "Old note." },
        { role: "review", content: "Tide Council committed as ent_0020." },
      ],
    });
    rerender(ui());
    expect(screen.getByText("Tide Council committed as ent_0020.")).toBeInTheDocument();
    expect(screen.queryByText("Old note.")).toBeNull();
    expect(screen.getByRole("link", { name: "Back to Review" })).toHaveAttribute("href", "/review");
    expect(screen.getByRole("link", { name: "Open in Chat" })).toHaveAttribute("href", "/chat/t1");
  });

  it("says nothing is waiting when the thread has nothing pending on load", () => {
    stream = base({ pending: null });
    render(ui());
    expect(screen.getByText("This conversation has nothing waiting for review.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Review" })).toHaveAttribute("href", "/review");
  });

  const OTHER = "This conversation belongs to another world. Switch worlds to review it.";

  it("says the conversation belongs to another world for a thread of another world", () => {
    stream = base({ pending: two, worldId: "w2" });
    render(ui());
    expect(screen.getByText(OTHER)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject all" })).toBeNull();
  });

  it("shows the other-world copy when the shown proposals carry another world_id", () => {
    const foreign = pendingOf([{ ...proposal("p_a", "Tide Council"), world_id: "w2" }, clean("p_a")]);
    stream = base({ pending: foreign, worldId: "w1" });
    render(ui());
    expect(screen.getByText(OTHER)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject all" })).toBeNull();
  });

  it("has exactly one main landmark", () => {
    render(ui());
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it("shows the hook's error instead of an empty outcome when the re-read fails", async () => {
    stream = base({
      pending: pendingOf([proposal("p_a", "Tide Council"), clean("p_a")]),
      chosen: { p_a: { proposal_id: "p_a", action: "approve" } },
    });
    const { rerender } = render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Submit 1 decision" }));
    stream = base({ pending: null, status: "error", error: "Lost the connection and could not reload." });
    rerender(ui());
    expect(screen.getByRole("alert")).toHaveTextContent("could not reload");
  });

  it("gives a proposal without a check a Check failed row and still submits it", async () => {
    const bare: PendingInterrupt = {
      proposals: [proposal("p_a", "Tide Council"), proposal("p_x", "Unchecked")],
      checks: { p_a: clean("p_a") },
    };
    const chosen: Record<string, Decision> = {
      p_a: { proposal_id: "p_a", action: "approve" },
      p_x: { proposal_id: "p_x", action: "reject" },
    };
    stream = base({ pending: bare, chosen });
    render(ui());
    const row = screen.getByRole("button", { name: /Unchecked/ });
    expect(within(row).getByText("Check failed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Submit 2 decisions" }));
    expect(stream.decide).toHaveBeenCalledWith([chosen.p_a, chosen.p_x]);
  });

  it("masks a keyless duplicate note in the queue like the card does", async () => {
    const dup = (entry: string, title: string): CheckResult => ({
      proposal_id: "x", verdict: "none", badge: "note", dependents: [],
      flags: [
        {
          ...conflictFlag, kind: "note", entry_id: entry, fact_key: null, existing_fact: null, new_fact: null,
          severity: null, explanation: `Possible duplicate of ${entry} '${title}'`,
        },
      ],
    });
    const entry = (id: string, title: string, secret: boolean) =>
      ({
        id, title, type: "place", status: "canon",
        facts: secret ? [{ key: "Members", value: "x", refs: [], status: "secret", told_by: null }] : [],
      }) as unknown as Entry;
    vi.mocked(getEntries).mockResolvedValue([entry("ent_0012", "Ister", true), entry("ent_0013", "Plain", false)]);
    stream = base({
      pending: pendingOf(
        [proposal("p_s", "Hides"), { ...dup("ent_0012", "Ister"), proposal_id: "p_s" }],
        [proposal("p_o", "Shows"), { ...dup("ent_0013", "Plain"), proposal_id: "p_o" }],
      ),
    });
    render(ui());
    // Once canon has loaded the plain entry's title shows; the one holding a secret fact stays hidden.
    expect(await screen.findByText("Possible duplicate of ent_0013 'Plain'")).toBeInTheDocument();
    expect(screen.getByText("Possible duplicate of ent_0012")).toBeInTheDocument();
    expect(screen.queryByText(/'Ister'/)).toBeNull();
  });

  it("names a secret draft Secret entry in the queue, with no type dot", () => {
    const ledger: Proposal = {
      ...proposal("p_s", "The Choir Ledger"),
      after: { title: "The Choir Ledger", type: "item", body: "", status: "secret", aliases: [], facts: [] },
    };
    stream = base({ pending: pendingOf([ledger, clean("p_s")], [proposal("p_o", "Tide Council"), clean("p_o")]) });
    render(ui());
    const queue = screen.getByRole("complementary", { name: "Pending proposals" });
    const rows = within(queue).getAllByRole("listitem");
    expect(within(rows[0]).getByText("Secret entry")).toBeInTheDocument();
    expect(within(rows[0]).queryByText("The Choir Ledger")).toBeNull();
    expect(rows[0].querySelector('[aria-hidden="true"].rounded-full')).toBeNull();
    expect(within(rows[1]).getByText("Tide Council")).toBeInTheDocument();
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
  });
});

describe("ReviewDetail for an import thread", () => {
  const note = {
    source: "notes.md",
    first_lines: { p_a: "The Tide Council sits at dusk." },
    skipped: [{ title: "Old Mill", reason: "couldn't locate the original text" }],
  };
  const importStream = (over: Partial<AgentStream> = {}) =>
    base({ kind: "import", title: "notes.md", importNote: note, ...over });

  it("shows where the selected card came from, the skipped list and the course chip", () => {
    stream = importStream({ pending: two });
    render(ui());
    expect(screen.getByText("From notes.md: \u201cThe Tide Council sits at dusk.\u201d")).toBeInTheDocument();
    const list = screen.getByRole("region", { name: "Not imported" });
    expect(within(list).getByText("Old Mill")).toBeInTheDocument();
    expect(within(list).getByText(/couldn't locate the original text/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Course note: Injection-safe extraction" })).toHaveAttribute(
      "href",
      "/studio?card=injection_safe_extraction#feature-map",
    );
  });

  it("offers Back to Import, not Open in Chat, once the decisions are in", async () => {
    const one = pendingOf([proposal("p_a", "Tide Council"), clean("p_a")]);
    stream = importStream({ pending: one, chosen: { p_a: { proposal_id: "p_a", action: "approve" } } });
    const { rerender } = render(ui());
    await userEvent.click(screen.getByRole("button", { name: "Submit 1 decision" }));
    stream = importStream({
      pending: null,
      messages: [{ role: "review", content: "Tide Council committed as ent_0020." }],
    });
    rerender(ui());
    expect(screen.getByText("Tide Council committed as ent_0020.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open in Chat" })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to Import" })).toHaveAttribute("href", "/import");
    expect(screen.getByRole("link", { name: "Back to Review" })).toBeInTheDocument();
  });

  it("shows a decided import's notes when opened later, with no submit in this session", () => {
    stream = importStream({
      pending: null,
      messages: [
        { role: "import", content: "Imported text: 2 proposals for review, 1 not imported." },
        { role: "review", content: "Tide Council committed as ent_0020." },
        { role: "review", content: "Sky of Velmar rejected." },
      ],
    });
    render(ui());
    expect(screen.queryByText("Nothing from this import needs review.")).toBeNull();
    const notes = screen.getByRole("list", { name: "Decision notes" });
    expect(within(notes).getByText("Tide Council committed as ent_0020.")).toBeInTheDocument();
    expect(within(notes).getByText("Sky of Velmar rejected.")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Not imported" })).getByText("Old Mill")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Review" })).toHaveAttribute("href", "/review");
    expect(screen.getByRole("link", { name: "Back to Import" })).toHaveAttribute("href", "/import");
    expect(screen.queryByRole("link", { name: "Open in Chat" })).toBeNull();
  });

  it("says nothing needs review when the import has no proposals, and lists what was left out", () => {
    stream = importStream({ pending: null });
    render(ui());
    expect(screen.getByText("Nothing from this import needs review.")).toBeInTheDocument();
    expect(screen.queryByText(/nothing waiting/)).toBeNull();
    expect(screen.getByText("Old Mill")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open in Chat" })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to Import" })).toHaveAttribute("href", "/import");
  });
});

describe("ReviewDetail for a wiki import thread", () => {
  const manifest = JSON.parse(
    readFileSync(join(__dirname, "../../api/tests/fixtures/wiki/manifest.json"), "utf-8"),
  ) as { licence: { text: string } };
  const LICENCE = manifest.licence.text;
  const GANDALF = "https://en.wikipedia.org/wiki/Gandalf";
  const source = (nc: boolean, licence: string | null = LICENCE) => ({
    kind: "official" as const, url: GANDALF, licence, licence_url: null, nc,
  });
  const wikiProposal = (id: string, title: string, nc = false, status: "canon" | "secret" = "canon"): Proposal => ({
    ...proposal(id, title),
    after: {
      title, type: "character", body: "A wizard.", status, aliases: [], facts: [], source: "official",
      source_url: GANDALF, licence: LICENCE, trusted: false, sources: [source(nc)],
    },
  });
  const note = {
    kind: "wiki" as const, source: "en.wikipedia.org", licence: { text: LICENCE, url: null, nc: false },
    first_lines: {}, skipped: [
      { title: "Moria", reason: "the page does not exist", paste: true },
      { title: "Orodruin", reason: "the page has no article text", paste: false },
    ],
  };
  const wikiStream = (pending: PendingInterrupt, over: Partial<AgentStream> = {}) =>
    base({ kind: "import", title: "Fan wiki: en.wikipedia.org (1 pages)", importNote: note, pending, ...over });
  const one = (nc = false, status: "canon" | "secret" = "canon") =>
    pendingOf([wikiProposal("p_g", "Gandalf", nc, status), clean("p_g")]);

  it("shows the licence, the page URL above the card and the course chip", () => {
    stream = wikiStream(one());
    render(ui());
    expect(screen.getByText(`Licence: ${LICENCE}`, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText(`From ${GANDALF}`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Course note: Official canon · licence" })).toHaveAttribute(
      "href",
      "/studio?card=official_canon_licence#feature-map",
    );
    expect(screen.queryByRole("link", { name: /Injection-safe/ })).toBeNull();
    expect(screen.queryByText(/Non-commercial licence/)).toBeNull();
  });

  it("says licence not reported when the wiki reported none", () => {
    stream = wikiStream(one(), { importNote: { ...note, licence: { text: null, url: null, nc: false } } });
    render(ui());
    expect(screen.getByText("Licence: licence not reported", { selector: "p" })).toBeInTheDocument();
  });

  it("warns above the queue when a source is non-commercial", () => {
    stream = wikiStream(pendingOf([wikiProposal("p_g", "Gandalf", true), clean("p_g")]));
    render(ui());
    expect(screen.getByText(
      `Non-commercial licence. Some of these pages are licensed for non-commercial use only (${LICENCE}). Approving them means this world can't be used commercially.`,
    )).toBeInTheDocument();
  });

  it("warns for chat-tool proposals too, whatever the thread kind", () => {
    stream = base({ pending: pendingOf([wikiProposal("p_g", "Gandalf", true), clean("p_g")]) });
    render(ui());
    expect(screen.getByText(/^Non-commercial licence\./)).toBeInTheDocument();
    expect(screen.queryByText(/^Licence:/, { selector: "p" })).toBeNull();
  });

  it("shows the licence URL when the wiki reported only a URL", () => {
    const url = "https://creativecommons.org/licenses/by-sa/4.0/";
    stream = wikiStream(one(), { importNote: { ...note, licence: { text: null, url, nc: false } } });
    render(ui());
    expect(screen.getByText(`Licence: ${url}`, { selector: "p" })).toBeInTheDocument();
  });

  it("names the page being imported, not an earlier reference source, on a merge", () => {
    const REF = "https://en.wikipedia.org/wiki/Wizard";
    const reference = { ...source(false), kind: "reference" as const, url: REF };
    const merged = wikiProposal("p_g", "Gandalf");
    merged.after = { ...merged.after!, sources: [reference, source(false)] };
    stream = wikiStream(pendingOf([merged, clean("p_g")]));
    render(ui());
    expect(screen.getByText(`From ${GANDALF}`)).toBeInTheDocument();
    expect(screen.queryByText(`From ${REF}`)).toBeNull();
  });

  it("does not show the URL of a hidden secret entry", () => {
    stream = wikiStream(one(false, "secret"));
    render(ui());
    expect(screen.queryByText(`From ${GANDALF}`)).toBeNull();
    expect(screen.queryByText(/wikipedia\.org\/wiki\/Gandalf/)).toBeNull();
  });

  it("links a skipped row to the paste card only where pasting can help", () => {
    stream = wikiStream(one());
    render(ui());
    const list = within(screen.getByRole("region", { name: "Not imported" }));
    expect(list.getAllByRole("link", { name: "Paste the text instead" })).toHaveLength(1);
    expect(list.getByRole("link", { name: "Paste the text instead" })).toHaveAttribute("href", "/import#paste");
    expect(within(list.getByText("Orodruin").closest("li") as HTMLElement).queryByRole("link")).toBeNull();
  });

  it("keeps From paste and the Injection-safe chip for a text import", () => {
    stream = base({
      kind: "import", title: "notes.md", pending: two,
      importNote: { kind: "text", source: "paste", first_lines: { p_a: "The Tide Council sits." }, skipped: [] },
    });
    render(ui());
    expect(screen.getByText("From paste: \u201cThe Tide Council sits.\u201d")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Course note: Injection-safe extraction" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Official canon/ })).toBeNull();
    expect(screen.queryByText(/^Licence:/)).toBeNull();
  });
});
