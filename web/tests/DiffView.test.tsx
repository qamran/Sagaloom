import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BodyDiff, LineDiff } from "@/components/DiffView";

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
