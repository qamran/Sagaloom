import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BodyDiff, LineDiff } from "@/components/DiffView";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));

describe("BodyDiff", () => {
  it("marks removed words in <del> and added words in <ins>", () => {
    const { container } = render(
      <BodyDiff before="The council has seven seats." after="The council has five seats." secret={false} />,
    );
    const details = container.querySelector("details");
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("Body changes")).toBeInTheDocument();
    expect(container.querySelector("del")).toHaveTextContent("removed: seven");
    expect(container.querySelector("ins")).toHaveTextContent("added: five");
  });

  it("renders nothing when the bodies are equal", () => {
    const { container } = render(<BodyDiff before="Same." after="Same." secret={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("LineDiff", () => {
  it("strikes the old title and highlights the new one", () => {
    render(<LineDiff changes={[{ field: "title", old: "Harbour Council", new: "Tide Council" }]} />);
    expect(screen.getByText("Harbour Council")).toHaveClass("line-through");
    expect(screen.getByText("Tide Council")).toHaveClass("bg-accent/15");
  });

  it("labels types and joins aliases", () => {
    render(
      <LineDiff
        changes={[
          { field: "type", old: "faction", new: "place" },
          { field: "aliases", old: "the Council", new: "the Council, the Seven" },
        ]}
      />,
    );
    expect(screen.getByText("Faction")).toHaveClass("line-through");
    expect(screen.getByText("Place")).toBeInTheDocument();
    expect(screen.getByText("the Council, the Seven")).toBeInTheDocument();
  });
});

describe("BodyDiff and LineDiff secrets", () => {
  it("BodyDiff is revealed when the world toggle is on", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    const { container } = render(<BodyDiff before="a b" after="a c" secret />);
    expect(container.querySelector("ins")).toBeInTheDocument();
  });

  it("BodyDiff stays masked with the toggle off", () => {
    const { container } = render(<BodyDiff before="a b" after="a c" secret />);
    expect(container.querySelector("ins")).toBeNull();
  });

  const changes = [
    { field: "title" as const, old: "Ledger", new: "Choir Ledger" },
    { field: "aliases" as const, old: "", new: "the Book" },
  ];

  it("LineDiff with secret masks title and alias values behind one Show", async () => {
    render(<LineDiff changes={changes} secret />);
    expect(screen.queryByText("Ledger")).toBeNull();
    expect(screen.queryByText("the Book")).toBeNull();
    expect(screen.getAllByRole("button", { name: /show/i })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /show/i }));
    expect(screen.getByText("Choir Ledger")).toBeInTheDocument();
    expect(screen.getByText("the Book")).toBeInTheDocument();
  });

  it("LineDiff with secret is revealed by the world toggle", () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    render(<LineDiff changes={changes} secret />);
    expect(screen.getByText("Choir Ledger")).toBeInTheDocument();
  });
});
