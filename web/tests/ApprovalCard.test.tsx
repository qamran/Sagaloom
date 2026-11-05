import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard, CHECK_FAILED_TEXT } from "@/components/ApprovalCard";
import type { CheckResult, Entry, Fact, Flag, Proposal } from "@/lib/types";

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
  links: [], facts: [fact("Moons", "One")], version: 3, created_at: "", updated_at: "",
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
  kind: "conflict", fact_key: "Moons", existing_fact: "One", new_fact: "Three", severity: "hard",
  explanation: "Ister is the only moon.",
  suggested_fix: "Keep one moon, and save three moons as a myth told by the Ashen Choir.",
});
const retcon = flag({
  kind: "retcon", entry_id: "ent_0007", title: "Sky of Velmar", fact_key: "Moons",
  existing_fact: "One", new_fact: "Three", explanation: "Changes this entry's own fact.",
});
const note = flag({
  kind: "note", severity: "note", existing_quote: "the only light in the night sky",
  new_quote: "three moons rise together", explanation: "Worth a look.",
});

const check = (verdict: CheckResult["verdict"], flags: Flag[]): CheckResult => ({
  proposal_id: "p_1", verdict, flags, dependents: [],
});

// A loaded, non-secret Ister: cited values may be shown.
const ister = {
  ...before, id: "ent_0012", title: "Ister", type: "place", facts: [fact("Moons", "One")],
} as Entry;

describe("ApprovalCard", () => {
  it("carries the human-in-the-loop course chip", () => {
    render(<ApprovalCard proposal={update} check={check("none", [])} onDecide={vi.fn()} />);
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
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} onDecide={onDecide} />);
    const save = screen.getByRole("button", { name: "Save as myth" });
    expect(save.tagName).toBe("BUTTON");
    await userEvent.click(save);
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ proposal_id: "p_1", action: "save_as_myth" }),
    );
  });

  it("ApprovalCard Save as myth passes an optional teller", async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} onDecide={onDecide} />);
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
    render(<ApprovalCard proposal={update} check={check("failed", [failed])} onDecide={vi.fn()} />);
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
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} onDecide={onDecide} />);
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

  it("ApprovalCard lists the proposal's drafted facts", async () => {
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} onDecide={vi.fn()} />);
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
    render(<ApprovalCard proposal={update} check={check("none", [retcon])} onDecide={vi.fn()} />);
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
    render(<ApprovalCard proposal={update} check={check("none", [])} onDecide={onDecide} />);
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
    expect(within(table).queryByText(/^One/)).toBeNull();
    await userEvent.click(within(table).getByRole("button", { name: /show secret fact/i }));
    expect(within(table).getByText(/^One/)).toBeInTheDocument();
  });

  it("uses real buttons at least 44px tall", () => {
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict])} onDecide={vi.fn()} />);
    for (const name of ["Save as myth", "Edit", "Approve anyway", "Reject"]) {
      expect(screen.getByRole("button", { name })).toHaveClass("min-h-11");
    }
  });

  it("fails closed while canon is not loaded: cross-entry values, quotes and titles stay hidden", async () => {
    render(<ApprovalCard proposal={update} check={check("conflict", [conflict, note])} onDecide={vi.fn()} />);
    const table = screen.getByRole("table");
    expect(within(table).queryByText(/^One/)).toBeNull();
    expect(screen.queryByText("Ister")).toBeNull();
    expect(screen.queryByText(/the only light in the night sky/)).toBeNull();
    expect(screen.getAllByText("hidden secret").length).toBeGreaterThanOrEqual(3);
    // IDs are still cited (R4.3), and Show reveals the value.
    expect(within(table).getByText("ent_0012")).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: /show secret fact/i }));
    expect(within(table).getByText(/^One/)).toBeInTheDocument();
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
    render(<ApprovalCard proposal={update} check={check("conflict", [plain])} canon={[ister]} onDecide={vi.fn()} />);
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
});
