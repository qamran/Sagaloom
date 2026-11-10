import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImportProgress } from "@/components/ImportProgress";

describe("ImportProgress", () => {
  it("announces progress in a status region", () => {
    render(<ImportProgress phase="extracting" candidates={1} skipped={0} events={[]} />);
    const status = screen.getByRole("status");
    expect(within(status).getByText("Found 1 candidate (0 not imported)")).toBeInTheDocument();
    expect(within(status).getByRole("list")).not.toHaveAttribute("role");
    expect(screen.getAllByRole("list")).toHaveLength(1);
  });

  it("shows the checking line once checking starts", () => {
    const { rerender } = render(<ImportProgress phase="extracting" candidates={2} skipped={1} events={[]} />);
    expect(screen.queryByText(/^Checking/)).toBeNull();
    rerender(<ImportProgress phase="checking" candidates={2} skipped={1} events={[]} />);
    expect(screen.getByText("Checking 2 proposals against canon…")).toBeInTheDocument();
  });
});
