import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "@/components/ApprovalCard";
import { CHECK_FAILED_TEXT } from "@/lib/review";
import { ReviewQueue } from "@/components/ReviewQueue";
import { SecretsWorldProvider, SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { CheckResult, Entry, Fact, Flag, Proposal } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

const fact = (key: string, value: string, status: Fact["status"] = "canon"): Fact => ({
  key,
  value,
  refs: ["ent_0012"],
  status,
  told_by: null,
});

const before = {
  id: "ent_0007", world_id: "w1", title: "Sky of Velmar", type: "place", body: "One red moon.",
  status: "canon", source: "user", source_url: null, licence: null, trusted: true, aliases: ["the sky"],
  links: [], facts: [fact("Moons", "Just one")], version: 3, created_at: "", updated_at: "",
} as Entry;

const update: Proposal = {
  proposal_id: "p_1",
  action: "update",
  world_id: "w1",
  entry_id: "ent_0007",
  before,
  after: {
    title: "Sky of Velmar",
    type: "place",
    body: "Three moons rise together at the solstice.",
    status: "canon",
    aliases: ["the sky"],
    facts: [fact("Moons", "Three"), fact("Hidden truth", "The moons are lanterns", "secret")],
  },
};

const flag = (over: Partial<Flag>): Flag => ({
  kind: "conflict", entry_id: "ent_0012", title: "Ister", fact_key: null, existing_fact: null,
  new_fact: null, existing_quote: null, new_quote: null, severity: null, explanation: "",
  suggested_fix: null, existing_secret: false, ...over,
});

const conflict = flag({
  kind: "conflict", fact_key: "Moons", existing_fact: "Moons: One", new_fact: "Moons: Three", severity: "hard",
  explanation: "Ister is the only moon.",
  suggested_fix: "Keep one moon, and save three moons as a myth told by the Ashen Choir.",
});
const retcon = flag({
  kind: "retcon", entry_id: "ent_0007", title: "Sky of Velmar", fact_key: "Moons",
  existing_fact: "Just one", new_fact: "Three", explanation: "Changes this entry's own fact.",
});
const note = flag({
  kind: "note", severity: "note", existing_quote: "the only light in the night sky",
  new_quote: "three moons rise together", explanation: "Worth a look.",
});

const check = (verdict: CheckResult["verdict"], flags: Flag[]): CheckResult => ({
  proposal_id: "p_1", verdict, flags, dependents: [],
});

/** The cell of `table` in the row whose Fact is `key`; column 1 is In canon, 2 Proposed. */
const cellOf = (table: HTMLElement, key: string, col: number) => {
  const row = within(table).getAllByRole("row").find((r) => within(r).queryByText(key)) as HTMLElement;
  return within(row).getAllByRole("cell")[col];
};

/** The citation (chip or mask, then the ID) of entry `id` inside the fact table. */
const citationOf = (id: string) => within(screen.getByRole("table")).getByText(id).parentElement as HTMLElement;

// A loaded, non-secret Ister: cited values may be shown.
const ister = {
  ...before, id: "ent_0012", title: "Ister", type: "place", facts: [fact("Moons", "One")],
} as Entry;

describe("ApprovalCard", () => {
  it("carries the human-in-the-loop course chip", () => {
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Course note: Human-in-the-loop · interrupt()" })).toHaveAttribute(
      "href",
      "/studio?card=human_in_the_loop#feature-map",
    );
  });

  it("ApprovalCard shows Conflict, Retcon and Note badges with entry ids", () => {
    render(
      <ApprovalCard
        proposal={update}
        check={check("conflict", [conflict, retcon, note])}
        canon={[ister]}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByText("Commit to canon?")).toBeInTheDocument();
    const badges = screen.getByRole("list", { name: "Check result" });
    expect(within(badges).getByText("Conflict")).toBeInTheDocument();
    expect(within(badges).getByText("Retcon")).toBeInTheDocument();
    expect(within(badges).getByText("Note")).toBeInTheDocument();
    // Fact table: Fact · In canon · Proposed, citing the entry and its ID.
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "In canon" })).toBeInTheDocument();
    expect(within(table).getAllByText(/ent_0012/).length).toBeGreaterThan(0);
    expect(within(table).getAllByText(/ent_0007/).length).toBeGreaterThan(0);
    // Prose quote for the note, citing Ister and its ID.
    expect(screen.getByText(/the only light in the night sky/)).toBeInTheDocument();
    expect(screen.getByText(/Keep one moon/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve anyway" })).toBeInTheDocument();
  });

  it("ApprovalCard Save as myth calls onDecide with save_as_myth", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} canon={[]} onDecide={onDecide} />);
    const save = screen.getByRole("button", { name: "Save as myth" });
    expect(save.tagName).toBe("BUTTON");
    await userEvent.click(save);
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ proposal_id: "p_1", action: "save_as_myth" }),
    );
  });

  it("ApprovalCard Save as myth passes an optional teller", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} canon={[]} onDecide={onDecide} />);
    await userEvent.type(screen.getByLabelText(/told by/i), "The Ashen Choir");
    await userEvent.click(screen.getByRole("button", { name: "Save as myth" }));
    expect(onDecide).toHaveBeenCalledWith({
      proposal_id: "p_1",
      action: "save_as_myth",
      told_by: "The Ashen Choir",
    });
  });

  it("ApprovalCard shows check-failed warning and no Save as myth", () => {
    const failed = flag({ kind: "note", entry_id: "", title: "", explanation: "The check failed." });
    render(<ApprovalCard proposal={update} check={check("failed", [failed])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getByText("Check failed")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The contradiction check couldn't run. Review this change yourself before approving.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save as myth" })).toBeNull();
    expect(screen.getByRole("button", { name: "Approve anyway" })).toBeInTheDocument();
    expect(screen.queryByText("No conflicts found")).toBeNull();
  });

  it("ApprovalCard edit submits edited draft", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} canon={[]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const title = screen.getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Sky over Velmar");
    const value = screen.getByLabelText("Fact 1 value");
    await userEvent.clear(value);
    await userEvent.type(value, "Two");
    await userEvent.selectOptions(screen.getByLabelText("Fact 1 status"), "myth");
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide).toHaveBeenCalledWith({
      proposal_id: "p_1",
      action: "edit",
      edited: {
        title: "Sky over Velmar",
        type: "place",
        body: "Three moons rise together at the solstice.",
        status: "canon",
        aliases: ["the sky"],
        facts: [
          { key: "Moons", value: "Two", refs: ["ent_0012"], status: "myth", told_by: null },
          { key: "Hidden truth", value: "The moons are lanterns", refs: ["ent_0012"], status: "secret", told_by: null },
        ],
      },
    });
  });

  it("ApprovalCard lists a new entry's drafted facts", async () => {
    const create: Proposal = { ...update, action: "create", entry_id: null, before: null };
    render(<ApprovalCard proposal={create} check={check("conflict", [conflict])} onDecide={vi.fn()} />);
    const drafted = screen.getByRole("region", { name: /drafted facts/i });
    expect(within(drafted).getByText("Moons")).toBeInTheDocument();
    expect(within(drafted).getByText("Three")).toBeInTheDocument();
    // Secret drafted facts stay hidden until Show (FactList).
    expect(screen.queryByText("The moons are lanterns")).toBeNull();
    await userEvent.click(within(drafted).getByRole("button", { name: /show secret fact/i }));
    expect(within(drafted).getByText("The moons are lanterns")).toBeInTheDocument();
    expect(screen.getAllByText("Sky of Velmar").length).toBeGreaterThan(0);
  });

  it("shows every retcon flag on a retcon-only card even though the verdict is none", () => {
    render(<ApprovalCard proposal={update} check={check("none", [retcon])} canon={[]} onDecide={vi.fn()} />);
    const badges = screen.getByRole("list", { name: "Check result" });
    expect(within(badges).getByText("Retcon")).toBeInTheDocument();
    expect(within(badges).queryByText("Conflict")).toBeNull();
    expect(screen.queryByText("No conflicts found")).toBeNull();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Moons")).toBeInTheDocument();
    expect(within(table).getAllByText(/ent_0007/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Save as myth" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve anyway" })).toBeInTheDocument();
  });

  it("offers a plain Approve and says no conflicts found when the check is clean", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={onDecide} />);
    expect(screen.getByText("No conflicts found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save as myth" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecide).toHaveBeenCalledWith({ proposal_id: "p_1", action: "approve" });
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecide).toHaveBeenLastCalledWith({ proposal_id: "p_1", action: "reject" });
  });

  it("lists dependents of a delete and offers no Edit or Save as myth", () => {
    const del: Proposal = { ...update, proposal_id: "p_2", action: "delete", after: null };
    render(
      <ApprovalCard
        proposal={del}
        check={{
          proposal_id: "p_2", verdict: "none", flags: [],
          dependents: [{ id: "ent_0003", title: "Captain Sorn", type: "character" }],
        }}
        canon={[]}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByText("These entries mention it:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Captain Sorn/ })).toHaveAttribute("href", "/canon/ent_0003");
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save as myth" })).toBeNull();
  });

  it("hides a cited secret canon fact in the table until Show", async () => {
    const secretIster = { ...ister, facts: [fact("Moons", "One", "secret")] } as Entry;
    render(
      <ApprovalCard
        proposal={update}
        check={check("conflict", [conflict])}
        canon={[secretIster]}
        onDecide={vi.fn()}
      />,
    );
    const table = screen.getByRole("table");
    expect(within(table).queryByText(/^Moons: One/)).toBeNull();
    const inCanon = cellOf(table, "Moons", 1);
    await userEvent.click(within(inCanon).getByRole("button", { name: /show secret fact/i }));
    expect(within(inCanon).getByText(/^Moons: One/)).toBeInTheDocument();
  });

  it("uses real buttons at least 44px tall", () => {
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} canon={[]} onDecide={vi.fn()} />);
    for (const name of ["Save as myth", "Edit", "Approve anyway", "Reject"]) {
      expect(screen.getByRole("button", { name })).toHaveClass("min-h-11");
    }
  });

  it("fails closed while canon is not loaded: cross-entry values, quotes and titles stay hidden", async () => {
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict, note])} onDecide={vi.fn()} />);
    // The own entry also hides until canon loads (it may be stored secret); its one Show opens it,
    // and the other entries' values stay hidden. It is first in the card; cited titles have their own.
    await userEvent.click(screen.getAllByRole("button", { name: "Show secret entry" })[0]);
    const table = screen.getByRole("table");
    expect(within(table).queryByText(/^Moons: One/)).toBeNull();
    expect(screen.queryByText("Ister")).toBeNull();
    expect(screen.queryByText(/the only light in the night sky/)).toBeNull();
    expect(screen.getAllByText("hidden secret").length).toBeGreaterThanOrEqual(3);
    // IDs are still cited (R4.3), and Show reveals the value.
    expect(within(table).getByText("ent_0012")).toBeInTheDocument();
    const inCanon = cellOf(table, "Moons", 1);
    await userEvent.click(within(inCanon).getByRole("button", { name: /show secret fact/i }));
    expect(within(inCanon).getByText(/^Moons: One/)).toBeInTheDocument();
  });

  it("masks a prose quote from an entry that holds a secret fact", async () => {
    const withSecret = { ...ister, facts: [fact("Moons", "One"), fact("Truth", "A lantern", "secret")] } as Entry;
    render(<ApprovalCard proposal={update} check={check("possible", [note])} canon={[withSecret]} onDecide={vi.fn()} />);
    expect(screen.queryByText(/the only light in the night sky/)).toBeNull();
    expect(screen.getByText("Ister")).toBeInTheDocument();
    const quote = screen.getByText(/In canon:/).closest("blockquote") as HTMLElement;
    await userEvent.click(within(quote).getByRole("button", { name: /show secret fact/i }));
    expect(screen.getByText(/the only light in the night sky/)).toBeInTheDocument();
  });

  it("masks the explanation and suggested fix of a flag the server marks secret", async () => {
    const secretFlag = flag({
      kind: "conflict", severity: "hard", existing_quote: "sings at every full moon",
      new_quote: "has never sung", explanation: "Ister sings at every full moon.",
      suggested_fix: "Drop the claim that Ister never sang.", existing_secret: true,
    });
    // Canon is loaded and holds no secret: only the server's existing_secret hides the text.
    render(<ApprovalCard proposal={update} check={check("conflict", [secretFlag])} canon={[ister]} onDecide={vi.fn()} />);
    expect(screen.queryByText(/sings at every full moon/)).toBeNull();
    expect(screen.queryByText(/Drop the claim/)).toBeNull();
    const fix = screen.getByText("Suggested fix:").parentElement as HTMLElement;
    await userEvent.click(within(fix).getByRole("button", { name: /show secret fact/i }));
    expect(screen.getByText("Drop the claim that Ister never sang.")).toBeInTheDocument();
  });

  it("shows the explanation and fix of a flag that cites no secret", () => {
    const plain = flag({
      kind: "conflict", severity: "hard", existing_quote: "one moon", new_quote: "three moons",
      explanation: "Ister is the only moon.", suggested_fix: "Keep one moon.",
    });
    // A draft with no secret fact: prose about it may be shown.
    const open: Proposal = { ...update, after: { ...update.after!, facts: [fact("Moons", "Three")] } };
    render(<ApprovalCard proposal={open} check={check("conflict", [plain])} canon={[ister]} onDecide={vi.fn()} />);
    expect(screen.getByText("Ister is the only moon.")).toBeInTheDocument();
    expect(screen.getByText("Keep one moon.")).toBeInTheDocument();
  });

  it("shows a failed update check's notice once, with Approve anyway kept secondary", () => {
    const notice = flag({
      kind: "note", entry_id: "ent_0007", title: "Sky of Velmar", severity: "note",
      explanation: "The check could not run. Review this change carefully before approving it.",
    });
    render(<ApprovalCard proposal={update} check={check("failed", [retcon, notice])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getByText(CHECK_FAILED_TEXT)).toBeInTheDocument();
    expect(screen.queryByText(/The check could not run/)).toBeNull();
    expect(within(screen.getByRole("list", { name: "Check result" })).queryByText("Note")).toBeNull();
    // Retcon flags still show on a failed check.
    expect(within(screen.getByRole("table")).getByText("Moons")).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "Approve anyway" });
    expect(approve).not.toHaveClass("bg-accent");
    expect(approve).toHaveClass("border-border-strong");
  });

  it("shows the reference source line with the Wikipedia URL as a safe link", () => {
    const url = "https://en.wikipedia.org/wiki/Venice";
    const ref: Proposal = {
      ...update,
      after: { ...update.after!, source: "reference", source_url: url, licence: null, trusted: false },
    };
    render(<ApprovalCard proposal={ref} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getByText("Source: reference (Wikipedia)")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: url });
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows the reference source line without a link when no URL was kept", () => {
    const ref: Proposal = {
      ...update,
      after: { ...update.after!, source: "reference", source_url: null, licence: null, trusted: false },
    };
    render(<ApprovalCard proposal={ref} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getByText("Source: reference (Wikipedia)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /wikipedia\.org/ })).not.toBeInTheDocument();
  });

  it("shows no source line for the author's own proposal", () => {
    const own: Proposal = { ...update, after: { ...update.after!, source: "user", source_url: null, trusted: true } };
    render(<ApprovalCard proposal={own} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.queryByText(/Source: reference/)).not.toBeInTheDocument();
  });
});

// ---------- the complete table (Wave 4) ----------

const entry = (over: Partial<Entry>): Entry =>
  ({
    world_id: "w1", type: "faction", body: "", status: "canon", source: "user", source_url: null, licence: null,
    trusted: true, aliases: [], links: [], facts: [], version: 1, created_at: "", updated_at: "", ...over,
  }) as Entry;

const updateOf = (e: Entry, after: Partial<Proposal["after"] & object>): Proposal => ({
  proposal_id: "p_1", action: "update", world_id: "w1", entry_id: e.id, before: e,
  after: { title: e.title, type: e.type, body: e.body, status: e.status, aliases: e.aliases, facts: e.facts, ...after },
});

const council = entry({
  id: "ent_0002", title: "Harbour Council", body: "Seven seats govern the harbour.",
  facts: [fact("Seats", "Seven"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr")],
});
const fiveSeats = updateOf(council, {
  facts: [fact("Seats", "Five"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr")],
});
const seatsRetcon = flag({
  kind: "retcon", entry_id: "ent_0002", title: "Harbour Council", fact_key: "Seats", existing_fact: "Seven",
  new_fact: "Five", explanation: "Changes established canon: Seven → Five",
  suggested_fix: "Keep seven seats and mark two as vacant.",
});
const rowOf = (table: HTMLElement, key: string) =>
  within(table).getAllByRole("row").find((r) => within(r).queryByText(key)) as HTMLElement;

describe("ApprovalCard complete table", () => {
  it("shows the complete table on an update", () => {
    render(<ApprovalCard proposal={fiveSeats} check={check("none", [seatsRetcon])} canon={[council]} onDecide={vi.fn()} />);
    const table = screen.getByRole("table");
    for (const name of ["Fact", "In canon", "Proposed", "Result"]) {
      expect(within(table).getByRole("columnheader", { name })).toBeInTheDocument();
    }
    expect(within(table).getAllByText("Matches")).toHaveLength(2);
    expect(within(rowOf(table, "Seats")).getByText("Changed (retcon)")).toBeInTheDocument();
    // The fix sits in the row right under Seats, not pooled at the card bottom.
    const rows = within(table).getAllByRole("row");
    const under = rows[rows.indexOf(rowOf(table, "Seats")) + 1];
    expect(within(under).getByText("Suggested fix:")).toBeInTheDocument();
    expect(within(under).getByText("Keep seven seats and mark two as vacant.")).toBeInTheDocument();
    expect(screen.getAllByText("Suggested fix:")).toHaveLength(1);
    // The table is complete: no separate drafted-facts list on an update.
    expect(screen.queryByRole("region", { name: /drafted facts/i })).toBeNull();
  });

  it("labels a possible conflict", () => {
    const possible = flag({
      kind: "conflict", severity: "possible", fact_key: "Moons", existing_fact: "Moons: One", new_fact: "Moons: Three",
      explanation: "Ister may be the only moon.",
    });
    render(<ApprovalCard proposal={update} check={check("possible", [possible])} canon={[ister]} onDecide={vi.fn()} />);
    const badges = screen.getByRole("list", { name: "Check result" });
    expect(within(badges).getByText("Possible conflict")).toBeInTheDocument();
    expect(within(badges).queryByText("Conflict")).toBeNull();
    expect(within(screen.getByRole("table")).getByText("Possible conflict")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save as myth" })).toBeInTheDocument();
  });

  it("masks own secret facts in the complete table", async () => {
    const mayor = entry({
      id: "ent_0003", title: "Mayor Elsbeth Varr", type: "character", body: "Mayor of Velmar.",
      facts: [fact("Age", "54"), fact("Sings with the Ashen Choir", "Yes, at every full Ister", "secret")],
    });
    const older = updateOf(mayor, {
      facts: [fact("Age", "55"), fact("Sings with the Ashen Choir", "Yes, at every full Ister", "secret")],
    });
    render(<ApprovalCard proposal={older} check={check("none", [])} canon={[mayor]} onDecide={vi.fn()} />);
    const table = screen.getByRole("table");
    expect(within(table).getByText("55")).toBeInTheDocument();
    expect(screen.queryByText("Yes, at every full Ister")).toBeNull();
    expect(screen.queryByText("Sings with the Ashen Choir")).toBeNull();
    const secretRow = within(table).getByText("Matches").closest("tr") as HTMLElement;
    const [keyCell, inCanon] = within(secretRow).getAllByRole("cell");
    expect(within(keyCell).getByRole("button", { name: /show secret fact/i })).toBeInTheDocument();
    await userEvent.click(within(inCanon).getByRole("button", { name: /show secret fact/i }));
    expect(within(inCanon).getByText("Yes, at every full Ister")).toBeInTheDocument();
    // Its status tag was hidden with the value and shows with it.
    expect(within(inCanon).getByText("secret")).toBeInTheDocument();
  });

  it("masks only the secret retcon row", () => {
    const choir = entry({
      id: "ent_0004", title: "Ashen Choir",
      facts: [fact("Members", "About sixty"), fact("Members", "Ashen Choir veterans", "secret")],
    });
    const grown = updateOf(choir, { facts: [fact("Members", "Several hundred")] });
    const common = flag({
      kind: "retcon", entry_id: "ent_0004", title: "Ashen Choir", fact_key: "Members", existing_fact: "About sixty",
      new_fact: "Several hundred", explanation: "Changes established canon: About sixty → Several hundred",
    });
    const hidden = flag({
      kind: "retcon", entry_id: "ent_0004", title: "Ashen Choir", fact_key: "Members",
      existing_fact: "Ashen Choir veterans", new_fact: "Several hundred", existing_secret: true,
      explanation: "Changes established canon: Ashen Choir veterans → Several hundred",
    });
    render(<ApprovalCard proposal={grown} check={check("none", [common, hidden])} canon={[choir]} onDecide={vi.fn()} />);
    const row = rowOf(screen.getByRole("table"), "Members");
    expect(within(row).getByText("About sixty")).toBeInTheDocument();
    expect(within(row).getAllByText("hidden secret")).toHaveLength(1);
    expect(screen.queryByText(/Ashen Choir veterans/)).toBeNull();
    expect(screen.getByText("Changes established canon: About sixty → Several hundred")).toBeInTheDocument();
  });

  it("masks the body diff of a secret entry", async () => {
    const vault = entry({ id: "ent_0020", title: "The Vault", status: "secret", body: "Gold lies under the quay." });
    render(
      <ApprovalCard
        proposal={updateOf(vault, { body: "Silver lies under the quay." })}
        check={check("none", [])}
        canon={[vault]}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByText("Body changes")).toBeInTheDocument();
    expect(screen.queryByText(/Silver/)).toBeNull();
    expect(screen.queryByText(/Gold/)).toBeNull();
    // The diff has no Show of its own: the card's one Show reveals it with the entry.
    expect(screen.queryByRole("button", { name: /show secret body/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.getByText(/Silver/)).toBeInTheDocument();
  });

  it("shows the title change and body diff above the table", () => {
    const renamed = updateOf(council, { title: "Tide Council", body: "Five seats govern the harbour." });
    render(<ApprovalCard proposal={renamed} check={check("none", [])} canon={[council]} onDecide={vi.fn()} />);
    expect(screen.getByText("Harbour Council")).toHaveClass("line-through");
    expect(document.querySelector("ins")).toHaveTextContent("Five");
  });

  it("never shows a secret proposed value through a retcon's explanation", () => {
    const choir = entry({ id: "ent_0004", title: "Ashen Choir", facts: [fact("Members", "About sixty")] });
    const grown = updateOf(choir, { facts: [fact("Members", "Lantern-bearers", "secret")] });
    const retconFlag = flag({
      kind: "retcon", entry_id: "ent_0004", title: "Ashen Choir", fact_key: "Members", existing_fact: "About sixty",
      new_fact: "Lantern-bearers", explanation: "Changes established canon: About sixty → Lantern-bearers",
      suggested_fix: "Keep Lantern-bearers as a rumour.",
    });
    render(<ApprovalCard proposal={grown} check={check("none", [retconFlag])} canon={[choir]} onDecide={vi.fn()} />);
    expect(screen.queryByText(/Lantern-bearers/)).toBeNull();
    expect(screen.getByText("About sixty")).toBeInTheDocument();
  });

  it("reads Changed and shows the myth tag when only the status changes", () => {
    const mythic = updateOf(council, {
      facts: [fact("Seats", "Seven", "myth"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr")],
    });
    render(<ApprovalCard proposal={mythic} check={check("none", [])} canon={[council]} onDecide={vi.fn()} />);
    const table = screen.getByRole("table");
    expect(within(rowOf(table, "Seats")).getByText("Changed")).toBeInTheDocument();
    expect(within(cellOf(table, "Seats", 2)).getByText("myth")).toBeInTheDocument();
    expect(within(cellOf(table, "Seats", 1)).queryByText("myth")).toBeNull();
  });

  it("shows who told a fact", () => {
    const told = updateOf(council, {
      facts: [
        { ...fact("Seats", "Nine", "myth"), told_by: "The Ashen Choir" },
        fact("Meets at", "The Tidehall"),
        fact("Chaired by", "Mayor Elsbeth Varr"),
      ],
    });
    render(<ApprovalCard proposal={told} check={check("none", [])} canon={[council]} onDecide={vi.fn()} />);
    expect(within(cellOf(screen.getByRole("table"), "Seats", 2)).getByText("told by The Ashen Choir")).toBeInTheDocument();
  });

  it("puts each other entry's value next to its own Cite, after this entry's values", () => {
    const guild = entry({ id: "ent_0011", title: "The Salt Guild", facts: [fact("Council seats", "Two of seven")] });
    const hard = flag({
      kind: "conflict", severity: "hard", entry_id: "ent_0011", title: "The Salt Guild", fact_key: "Seats", existing_fact: "Council seats: Two of seven", new_fact: "Seats: Five",
      explanation: "The Salt Guild holds two of seven seats.",
    });
    render(
      <ApprovalCard proposal={fiveSeats} check={check("conflict", [seatsRetcon, hard])} canon={[council, guild]} onDecide={vi.fn()} />,
    );
    const items = within(cellOf(screen.getByRole("table"), "Seats", 1)).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Seven");
    expect(items[0]).not.toHaveTextContent("ent_0002");
    expect(items[1]).toHaveTextContent("Two of seven");
    expect(within(items[1]).getByText("ent_0011")).toBeInTheDocument();
  });

  it("cites the other entry of a keyed note", () => {
    const keyedNote = flag({ kind: "note", severity: "note", entry_id: "ent_0011", title: "The Salt Guild", fact_key: "Seats", explanation: "Worth a look." });
    const guild = entry({ id: "ent_0011", title: "The Salt Guild" });
    render(<ApprovalCard proposal={fiveSeats} check={check("none", [keyedNote])} canon={[council, guild]} onDecide={vi.fn()} />);
    expect(within(cellOf(screen.getByRole("table"), "Seats", 1)).getByText("ent_0011")).toBeInTheDocument();
  });

  it("hides a secret new entry's body until Show", async () => {
    const create: Proposal = {
      ...update, action: "create", entry_id: null, before: null,
      after: { ...update.after!, status: "secret", body: "A hidden moon of glass." },
    };
    render(<ApprovalCard proposal={create} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.queryByText(/hidden moon of glass/)).toBeNull();
    // The body has no Show of its own: the card's one Show reveals it with the entry.
    const body = screen.getAllByText("hidden secret").map((e) => e.closest("p")).find(Boolean) as HTMLElement;
    expect(within(body).queryByRole("button")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.getByText("A hidden moon of glass.")).toBeInTheDocument();
  });

  it("no apply-fix button", () => {
    render(<ApprovalCard proposal={fiveSeats} check={check("none", [seatsRetcon])} canon={[council]} onDecide={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
  });

  it("edit form mirrors the schema limits", async () => {
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Title")).toHaveAttribute("maxLength", "120");
    expect(screen.getByLabelText("Body")).toHaveAttribute("maxLength", "4000");
    expect(screen.getByLabelText("Fact 1 key")).toHaveAttribute("maxLength", "40");
    expect(screen.getByLabelText("Fact 1 value")).toHaveAttribute("maxLength", "200");
  });
});

describe("ApprovalCard secret entries (Wave 7)", () => {
  const secretCreate: Proposal = {
    ...update, action: "create", entry_id: null, before: null,
    after: {
      title: "The Choir Ledger", type: "item", body: "", status: "secret", aliases: ["the Book"],
      facts: [fact("Holder", "The Mayor"), fact("Contents", "Names", "secret")],
    },
  };

  it("hides every drafted fact of a secret create, canon-status ones too", async () => {
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    const drafted = screen.getByRole("region", { name: /drafted facts/i });
    expect(within(drafted).queryByText("The Mayor")).toBeNull();
    expect(within(drafted).queryByText("Holder")).toBeNull();
    expect(within(drafted).getAllByText("Secret fact")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(within(drafted).getByText("The Mayor")).toBeInTheDocument();
  });

  it("the world toggle reveals a secret create's facts", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(within(screen.getByRole("region", { name: /drafted facts/i })).getByText("The Mayor")).toBeInTheDocument();
  });

  it("masks the line diff of a secret entry's update", () => {
    const secretBefore = { ...before, title: "Old Ledger", status: "secret" } as Entry;
    const proposal: Proposal = {
      ...update, before: secretBefore, after: { ...update.after!, title: "New Ledger", status: "secret" },
    };
    render(<ApprovalCard proposal={proposal} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    const row = screen.getByText("Title", { selector: "dt" }).closest("div") as HTMLElement;
    expect(within(row).queryByText("Old Ledger")).toBeNull();
    expect(within(row).queryByText("New Ledger")).toBeNull();
    expect(screen.queryByRole("button", { name: /show secret changes/i })).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Show/ })).toHaveLength(1);
  });

  it("hides a secret create's title in the header, the region name and the create block until the card's Show", async () => {
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByRole("region", { name: "Review proposal: secret entry" })).toBeInTheDocument();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    // The status line stays: "secret" is the status, not the secret.
    expect(screen.getByText(/Item · secret/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.getAllByText("The Choir Ledger")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Review proposal: The Choir Ledger" })).toBeInTheDocument();
  });

  it("the world toggle reveals a secret create's title", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.getAllByText("The Choir Ledger")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Show secret entry" })).toBeNull();
  });

  it("hides a secret update's header title when only the stored entry is secret", () => {
    const secretBefore = { ...before, title: "Old Ledger", status: "secret" } as Entry;
    const proposal: Proposal = { ...update, before: secretBefore, after: { ...update.after!, title: "Old Ledger" } };
    render(<ApprovalCard proposal={proposal} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.queryByText("Old Ledger")).toBeNull();
    expect(screen.getByRole("region", { name: "Review proposal: secret entry" })).toBeInTheDocument();
  });

  it("hides a secret entry's own title in a retcon citation until the card's Show or the world toggle", async () => {
    const secretBefore = { ...before, title: "Old Ledger", status: "secret", facts: [fact("Moons", "Just one")] } as Entry;
    const proposal: Proposal = { ...update, before: secretBefore, after: { ...update.after!, title: "Old Ledger", status: "secret" } };
    // Server shape (retcon.py): the flag cites the proposal's own entry by its stored title.
    const ownRetcon = flag({
      kind: "retcon", entry_id: "ent_0007", title: "Old Ledger", fact_key: "Moons",
      existing_fact: "Just one", new_fact: "Three", explanation: "Changes this entry's own fact.",
    });
    const ui = <ApprovalCard proposal={proposal} check={check("none", [ownRetcon])} canon={[]} onDecide={vi.fn()} />;
    render(ui);
    expect(screen.queryByText("Old Ledger")).toBeNull();
    // The header's Show is the one reveal; the own citation has none of its own.
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(within(citationOf("ent_0007")).getByText("Old Ledger")).toBeInTheDocument();
    cleanup();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(ui);
    expect(within(citationOf("ent_0007")).getByText("Old Ledger")).toBeInTheDocument();
  });

  it("names a secret dependent of a delete as Secret entry, with no link", () => {
    const ledger = { ...before, id: "ent_0019", title: "The Choir Ledger", type: "item", status: "secret" } as Entry;
    const del: Proposal = { ...update, proposal_id: "p_2", action: "delete", entry_id: "ent_0004", before: null, after: null };
    render(
      <ApprovalCard
        proposal={del}
        check={{
          proposal_id: "p_2", verdict: "none", flags: [],
          dependents: [
            { id: "ent_0019", title: "The Choir Ledger", type: "item" },
            { id: "ent_0003", title: "Captain Sorn", type: "character" },
          ],
        }}
        canon={[ledger]}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Secret entry/ })).toBeNull();
    expect(document.querySelector('a[href="/canon/ent_0019"]')).toBeNull();
    expect(screen.getByRole("link", { name: /Captain Sorn/ })).toBeInTheDocument();
  });

  it("names every dependent Secret entry until canon has loaded (fail closed)", async () => {
    const del: Proposal = { ...update, proposal_id: "p_2", action: "delete", after: null };
    render(
      <ApprovalCard
        proposal={del}
        check={{
          proposal_id: "p_2", verdict: "none", flags: [],
          dependents: [{ id: "ent_0003", title: "Captain Sorn", type: "character" }],
        }}
        onDecide={vi.fn()}
      />,
    );
    // The deleted entry hides until canon loads too; opening it leaves the dependent masked (Ruling 10).
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.queryByText("Captain Sorn")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
  });

  it("the edit form hides every fact value of a secret entry draft, canon-status ones too", async () => {
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    for (const n of [1, 2]) {
      expect(screen.getByLabelText(`Fact ${n} value`)).toBeDisabled();
      expect(screen.getByLabelText(`Fact ${n} value`)).toHaveValue("");
    }
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 1" }));
    expect(screen.getByLabelText("Fact 1 value")).toHaveValue("The Mayor");
  });
});

describe("ApprovalCard toggle follows the proposal's world", () => {
  const w2 = (p: Proposal): Proposal => ({ ...p, world_id: "w2", before: p.before && { ...p.before, world_id: "w2" } });
  const secretCreate: Proposal = w2({
    ...update, action: "create", entry_id: null, before: null,
    after: {
      title: "The Choir Ledger", type: "item", body: "Names of the Choir.", status: "secret", aliases: [],
      facts: [fact("Holder", "The Mayor")],
    },
  });

  it("keeps another world's secrets masked when only the active world's toggle is on", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.queryByText("The Mayor")).toBeNull();
    expect(screen.queryByText("Names of the Choir.")).toBeNull();
    const updateCard = w2(update);
    cleanup();
    render(<ApprovalCard proposal={updateCard} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.queryByText("The moons are lanterns")).toBeNull();
  });

  it("reveals them when that world's own toggle is on", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w2"), "true");
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.getByText("The Mayor")).toBeInTheDocument();
    expect(screen.getByText("Names of the Choir.")).toBeInTheDocument();
  });
});

describe("ApprovalCard secret leftovers (Wave 8)", () => {
  const choir = { ...before, id: "ent_0004", title: "The Ashen Choir", type: "faction" } as Entry;
  const mayor = { ...before, id: "ent_0003", title: "The Mayor", type: "character" } as Entry;
  const salt = { ...before, id: "ent_0011", title: "The Salt Guild", type: "faction" } as Entry;
  const del: Proposal = { ...update, proposal_id: "p_2", action: "delete", entry_id: "ent_0004", before: choir, after: null };
  const delCheck = (dependents: CheckResult["dependents"]): CheckResult => ({
    proposal_id: "p_2", verdict: "none", flags: [], dependents,
  });
  const mayorRef = { id: "ent_0003", title: "The Mayor", type: "character" as const, via: "link" as const };
  const saltRef = { id: "ent_0011", title: "The Salt Guild", type: "faction" as const, via: "text" as const };

  it("delete card counts a link-only dependent while secrets are hidden", () => {
    const { unmount } = render(
      <ApprovalCard proposal={del} check={delCheck([saltRef, mayorRef])} canon={[choir, mayor, salt]} onDecide={vi.fn()} />,
    );
    expect(screen.getByText("These entries mention it:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /The Salt Guild/ })).toBeInTheDocument();
    expect(screen.queryByText(/Mayor/)).toBeNull();
    expect(screen.queryByText("ent_0003")).toBeNull();
    expect(document.querySelector('a[href="/canon/ent_0003"]')).toBeNull();
    expect(screen.getByText("and 1 linked entry")).toBeInTheDocument();
    unmount();

    // With no text mentions, the count is the whole line.
    render(<ApprovalCard proposal={del} check={delCheck([mayorRef, { ...mayorRef, id: "ent_0099" }])} canon={[choir, mayor]} onDecide={vi.fn()} />);
    expect(screen.queryByText(/Mayor/)).toBeNull();
    expect(screen.queryByText("These entries mention it:")).toBeNull();
    expect(screen.queryByText("No other entries mention it.")).toBeNull();
    expect(screen.getByText("2 linked entries depend on it")).toBeInTheDocument();
    cleanup();
    render(<ApprovalCard proposal={del} check={delCheck([mayorRef])} canon={[choir, mayor]} onDecide={vi.fn()} />);
    expect(screen.getByText("1 linked entry depends on it")).toBeInTheDocument();
  });

  it("delete card names link-only dependents when the world shows secrets", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={del} check={delCheck([saltRef, mayorRef])} canon={[choir, mayor, salt]} onDecide={vi.fn()} />);
    const links = screen.getAllByRole("link", { name: /The Salt Guild|The Mayor/ });
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/canon/ent_0011", "/canon/ent_0003"]);
    expect(screen.queryByText(/linked entr/)).toBeNull();
  });

  it("delete card lists link-only dependents on their own line while shown", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    const varr = { ...mayorRef, title: "Mayor Elsbeth Varr" };
    render(<ApprovalCard proposal={del} check={delCheck([saltRef, varr])} canon={[choir, mayor, salt]} onDecide={vi.fn()} />);
    const mention = screen.getByText("These entries mention it:");
    const linkLine = screen.getByText("These entries link to it:");
    const salted = screen.getByRole("link", { name: /The Salt Guild/ });
    const linked = screen.getByRole("link", { name: /Mayor Elsbeth Varr/ });
    const follows = (a: Node, b: Node) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(mention, salted)).toBe(true);
    expect(follows(salted, linkLine)).toBe(true);
    expect(follows(linkLine, linked)).toBe(true);
    cleanup();
    // Only link-only dependents: no "mention it" line at all.
    render(<ApprovalCard proposal={del} check={delCheck([varr])} canon={[choir, mayor]} onDecide={vi.fn()} />);
    expect(screen.queryByText("These entries mention it:")).toBeNull();
    expect(screen.getByText("These entries link to it:")).toBeInTheDocument();
  });

  const secretUpdate: Proposal = {
    ...update,
    before: { ...before, title: "The Choir Ledger", body: "Kept under the Mayor's floor.", status: "secret" } as Entry,
    after: { ...update.after!, title: "The Choir Ledger", body: "Kept under the Mayor's floor.", status: "canon", facts: [] },
  };

  it("edit form masks a secret draft until Show to edit", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={secretUpdate} check={check("none", [])} canon={[]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByDisplayValue("The Choir Ledger")).toBeNull();
    expect(screen.queryByDisplayValue("Kept under the Mayor's floor.")).toBeNull();
    const title = screen.getByLabelText("Title");
    const body = screen.getByLabelText("Body");
    expect(title).toBeDisabled();
    expect(body).toBeDisabled();
    expect(title).toHaveAttribute("placeholder", "Secret entry: hidden");
    expect(body).toHaveAttribute("placeholder", "Secret entry: hidden");
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry to edit" }));
    expect(screen.getByLabelText("Title")).toHaveValue("The Choir Ledger");
    expect(screen.getByLabelText("Body")).toHaveValue("Kept under the Mayor's floor.");
    await userEvent.clear(screen.getByLabelText("Title"));
    await userEvent.type(screen.getByLabelText("Title"), "The Ledger");
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide.mock.calls[0][0].edited.title).toBe("The Ledger");
    cleanup();

    // The world toggle shows them without the per-form reveal.
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={secretUpdate} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Title")).toHaveValue("The Choir Ledger");
    expect(screen.queryByRole("button", { name: "Show secret entry to edit" })).toBeNull();
  });

  it("edit form hides a secret fact's key until that row's Show, and keeps it on submit", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Fact 1 key")).toHaveValue("Moons");
    const key = screen.getByLabelText("Fact 2 key");
    expect(key).toBeDisabled();
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("placeholder", "Secret fact");
    expect(screen.queryByDisplayValue("Hidden truth")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide.mock.calls[0][0].edited.facts[1].key).toBe("Hidden truth");
    cleanup();
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 2" }));
    expect(screen.getByLabelText("Fact 2 key")).toHaveValue("Hidden truth");
    expect(screen.getByLabelText("Fact 2 key")).toBeEnabled();
    cleanup();
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<ApprovalCard proposal={update} check={check("none", [])} canon={[]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Fact 2 key")).toHaveValue("Hidden truth");
  });

  it("Show to edit reveals facts hidden only because the stored entry is secret (R5)", async () => {
    // The draft is canon and so is the proposal's before; only the stored entry in canon is secret.
    const stored = { ...before, title: "The Choir Ledger", status: "secret" } as Entry;
    const proposal: Proposal = {
      ...update, before: { ...before, title: "The Choir Ledger" } as Entry,
      after: {
        ...update.after!, title: "The Choir Ledger",
        facts: [fact("Holder", "The Mayor"), fact("Contents", "Names", "secret")],
      },
    };
    render(<ApprovalCard proposal={proposal} check={check("none", [])} canon={[stored]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Title")).toBeDisabled();
    expect(screen.getByLabelText("Fact 1 key")).toBeDisabled();
    expect(screen.getByLabelText("Fact 1 value")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry to edit" }));
    expect(screen.getByLabelText("Title")).toHaveValue("The Choir Ledger");
    expect(screen.getByLabelText("Fact 1 key")).toHaveValue("Holder");
    expect(screen.getByLabelText("Fact 1 value")).toHaveValue("The Mayor");
    // A fact that is secret in its own right still needs its own Show.
    expect(screen.getByLabelText("Fact 2 key")).toBeDisabled();
    expect(screen.getByLabelText("Fact 2 value")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 2" }));
    expect(screen.getByLabelText("Fact 2 key")).toHaveValue("Contents");
  });

  it("submitting an unrevealed secret edit keeps title and body", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={secretUpdate} check={check("none", [])} canon={[]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide).toHaveBeenCalledWith({
      proposal_id: "p_1", action: "edit", edited: { ...secretUpdate.after!, facts: [] },
    });
  });
});

describe("ApprovalCard one Show per secret entry (M3 Wave 2)", () => {
  const mayor = entry({
    id: "ent_0003", title: "Mayor Elsbeth Varr", type: "character",
    facts: [fact("Holder", "Yes, at every full Ister", "secret"), fact("Age", "54")],
  });
  const older = updateOf(mayor, { facts: [fact("Holder", "Yes, at every full Ister", "secret"), fact("Age", "55")] });

  it("edit form puts no hidden value in the DOM", async () => {
    const { container } = render(<ApprovalCard proposal={older} check={check("none", [])} canon={[mayor]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(container.innerHTML).not.toContain("Yes, at every full Ister");
    expect(container.querySelector('input[type="password"]')).toBeNull();
    const value = screen.getByLabelText("Fact 1 value");
    expect(value).toBeDisabled();
    expect(value).toHaveAttribute("placeholder", "Secret fact");
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 1" }));
    expect(screen.getByLabelText("Fact 1 value")).toHaveValue("Yes, at every full Ister");
  });

  it("edit form locks a hidden row's status", async () => {
    render(<ApprovalCard proposal={older} check={check("none", [])} canon={[mayor]} onDecide={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Fact 1 status")).toBeDisabled();
    expect(screen.getByLabelText("Fact 2 status")).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 1" }));
    expect(screen.getByLabelText("Fact 1 status")).toBeEnabled();
  });

  it("submitting without Show keeps hidden facts exactly", async () => {
    const onDecide = vi.fn();
    // Padded and blank on purpose: a hidden row is sent as drafted, never trimmed or dropped.
    const told: Fact = {
      key: " Holder ", value: " Yes, at every full Ister ", refs: ["ent_0004"], status: "secret", told_by: "The Ashen Choir",
    };
    const blank: Fact = { key: "Unsaid", value: "", refs: [], status: "secret", told_by: null };
    const drafted = updateOf(mayor, { facts: [told, fact("Age", "55"), blank] });
    render(<ApprovalCard proposal={drafted} check={check("none", [])} canon={[mayor]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide.mock.calls[0][0].edited.facts).toEqual(drafted.after!.facts);
  });

  it("a revealed, edited, then re-hidden row is sent as it stands", async () => {
    const onDecide = vi.fn();
    const three = updateOf(mayor, {
      facts: [fact("Holder", "Yes, at every full Ister", "secret"), fact("Age", "55"), fact("Born", "Velmar")],
    });
    render(<ApprovalCard proposal={three} check={check("none", [])} canon={[mayor]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Show secret fact 1" }));
    await userEvent.clear(screen.getByLabelText("Fact 1 value"));
    await userEvent.type(screen.getByLabelText("Fact 1 value"), " Only at the red moon ");
    // Removing a row clears every reveal, so row 1 is hidden again with its edit in it.
    await userEvent.click(screen.getByRole("button", { name: "Remove fact 3" }));
    expect(screen.getByLabelText("Fact 1 value")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(onDecide.mock.calls[0][0].edited.facts).toEqual([
      { ...fact("Holder", " Only at the red moon ", "secret") },
      fact("Age", "55"),
    ]);
  });

  it("a stored secret update hides its fact table and diffs behind the card's one Show", async () => {
    // before and after are canon; only the stored entry in canon is secret now.
    const stored = { ...council, status: "secret" } as Entry;
    const renamed = updateOf(council, {
      title: "Tide Council", body: "Five seats govern the harbour.",
      facts: [
        fact("Seats", "Five"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr"),
        fact("Hidden truth", "The seats are empty", "secret"),
      ],
    });
    const { container } = render(
      <ApprovalCard proposal={renamed} check={check("none", [seatsRetcon])} canon={[stored]} onDecide={vi.fn()} />,
    );
    expect(container.textContent).not.toMatch(/Seven|Five|Tidehall|Elsbeth|Tide Council|Harbour Council|Seats|vacant/);
    expect(screen.getAllByRole("button", { name: /^Show/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Show secret entry" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    const table = screen.getByRole("table");
    expect(within(cellOf(table, "Seats", 1)).getByText("Seven")).toBeInTheDocument();
    expect(within(cellOf(table, "Seats", 2)).getByText("Five")).toBeInTheDocument();
    expect(screen.getByText("Harbour Council", { selector: ".line-through" })).toBeInTheDocument();
    expect(document.querySelector("ins")).toHaveTextContent("Five");
    expect(screen.getByText("Keep seven seats and mark two as vacant.")).toBeInTheDocument();
    // The fact that is secret in its own right keeps its own Show: exactly one on its value.
    expect(screen.queryByText("The seats are empty")).toBeNull();
    const proposedCell = within(within(table).getByText("New").closest("tr") as HTMLElement).getAllByRole("cell")[2];
    expect(within(proposedCell).getAllByRole("button", { name: /show secret fact/i })).toHaveLength(1);
    await userEvent.click(within(proposedCell).getByRole("button", { name: /show secret fact/i }));
    expect(within(proposedCell).getByText("The seats are empty")).toBeInTheDocument();
  });

  it("the card's one Show lifts a secret entry's own retcon, which the server marks existing_secret", async () => {
    const vault = { ...council, status: "secret" } as Entry;
    // Server shape (retcon.py): an own retcon on a secret entry is marked existing_secret.
    const marked = { ...seatsRetcon, existing_secret: true };
    render(
      <ApprovalCard proposal={updateOf(vault, fiveSeats.after!)} check={check("none", [marked])} canon={[vault]} onDecide={vi.fn()} />,
    );
    expect(screen.queryByText(/Seven/)).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Show/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.getByText("Changes established canon: Seven → Five")).toBeInTheDocument();
    expect(screen.getByText("Keep seven seats and mark two as vacant.")).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: /^Show/ })).toHaveLength(0);
  });

  it("a stored secret hides the card and the queue row", async () => {
    // before and after are canon; only the stored entry in canon is secret now.
    const stored = { ...before, title: "The Choir Ledger", status: "secret" } as Entry;
    const proposal: Proposal = {
      ...update, before: { ...before, title: "The Choir Ledger" } as Entry,
      after: { ...update.after!, title: "The Choir Ledger", facts: [fact("Moons", "Three")] },
    };
    const ownRetcon = flag({
      kind: "retcon", entry_id: "ent_0007", title: "The Choir Ledger", fact_key: "Moons",
      existing_fact: "Just one", new_fact: "Three", explanation: "Changes this entry's own fact.",
    });
    const result = check("none", [ownRetcon]);
    render(<ApprovalCard proposal={proposal} check={result} canon={[stored]} onDecide={vi.fn()} />);
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByRole("region", { name: "Review proposal: secret entry" })).toBeInTheDocument();
    expect(within(citationOf("ent_0007")).queryByRole("button")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Title")).toBeDisabled();
    cleanup();
    render(
      <SecretsWorldProvider worldId="w1">
        <ReviewQueue
          pending={{ proposals: [proposal], checks: { p_1: result } }}
          canon={[stored]}
          selectedId="p_1"
          chosen={{}}
          onSelect={vi.fn()}
        />
      </SecretsWorldProvider>,
    );
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
  });

  it("an update hides its entry until canon loads", () => {
    // before and after are canon, but the stored entry may have turned secret: unknown until canon loads.
    const proposal: Proposal = {
      ...update, before: { ...before, title: "The Choir Ledger" } as Entry,
      after: { ...update.after!, title: "The Choir Ledger", facts: [fact("Moons", "Three")] },
    };
    const result = check("none", []);
    const card = render(<ApprovalCard proposal={proposal} check={result} onDecide={vi.fn()} />);
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByRole("region", { name: "Review proposal: secret entry" })).toBeInTheDocument();
    card.rerender(<ApprovalCard proposal={proposal} check={result} canon={[proposal.before!]} onDecide={vi.fn()} />);
    expect(screen.getAllByText("The Choir Ledger").length).toBeGreaterThan(0);
    cleanup();
    const queue = (canon: Entry[] | undefined) => (
      <SecretsWorldProvider worldId="w1">
        <ReviewQueue
          pending={{ proposals: [proposal], checks: { p_1: result } }}
          canon={canon}
          selectedId="p_1"
          chosen={{}}
          onSelect={vi.fn()}
        />
      </SecretsWorldProvider>
    );
    const row = render(queue(undefined));
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
    expect(screen.getByText("Secret entry")).toBeInTheDocument();
    row.rerender(queue([proposal.before!]));
    expect(screen.getByText("The Choir Ledger")).toBeInTheDocument();
  });

  it("one Show reveals a secret create", async () => {
    const secretCreate: Proposal = {
      ...update, action: "create", entry_id: null, before: null,
      after: {
        title: "The Choir Ledger", type: "item", body: "Names of the Choir.", status: "secret", aliases: [],
        facts: [fact("Holder", "The Mayor"), fact("Contents", "Names", "secret")],
      },
    };
    render(<ApprovalCard proposal={secretCreate} check={check("none", [])} onDecide={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: "Show secret entry" })).toHaveLength(1);
    expect(screen.queryAllByRole("button", { name: /show secret fact/i })).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(screen.getAllByText("The Choir Ledger").length).toBeGreaterThan(0);
    expect(screen.getByText("Names of the Choir.")).toBeInTheDocument();
    expect(screen.getByText("The Mayor")).toBeInTheDocument();
    // The fact that is secret in its own right keeps its own Show.
    expect(screen.queryByText("Names")).toBeNull();
    expect(screen.getAllByRole("button", { name: /show secret fact/i })).toHaveLength(1);
  });

  it("own citation has no Show of its own", async () => {
    const secretBefore = { ...before, title: "Old Ledger", status: "secret", facts: [fact("Moons", "Just one")] } as Entry;
    const proposal: Proposal = { ...update, before: secretBefore, after: { ...update.after!, title: "Old Ledger", status: "secret" } };
    const ownRetcon = flag({
      kind: "retcon", entry_id: "ent_0007", title: "Old Ledger", fact_key: "Moons",
      existing_fact: "Just one", new_fact: "Three", explanation: "Changes this entry's own fact.",
    });
    render(<ApprovalCard proposal={proposal} check={check("none", [ownRetcon])} canon={[]} onDecide={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: "Show secret entry" })).toHaveLength(1);
    expect(within(citationOf("ent_0007")).queryByRole("button")).toBeNull();
    expect(within(citationOf("ent_0007")).queryByText("Old Ledger")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(within(citationOf("ent_0007")).getByText("Old Ledger")).toBeInTheDocument();
  });

  it("own prose-flag citation hides with the entry", async () => {
    const secretBefore = { ...before, title: "Old Ledger", status: "secret" } as Entry;
    const proposal: Proposal = { ...update, before: secretBefore, after: { ...update.after!, title: "Old Ledger", status: "secret" } };
    const ownNote = flag({ kind: "note", severity: "note", entry_id: "ent_0007", title: "Old Ledger", explanation: "Worth a look." });
    render(<ApprovalCard proposal={proposal} check={check("none", [ownNote])} canon={[]} onDecide={vi.fn()} />);
    const prose = screen.getByText("Note", { selector: "strong" }).parentElement as HTMLElement;
    expect(screen.queryByText("Old Ledger")).toBeNull();
    expect(within(prose).getByText("ent_0007")).toBeInTheDocument();
    expect(within(prose).queryByRole("button", { name: "Show secret entry" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show secret entry" }));
    expect(within(prose).getByText("Old Ledger")).toBeInTheDocument();
  });
});
