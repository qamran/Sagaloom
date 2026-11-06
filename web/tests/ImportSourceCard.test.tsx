import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImportSourceCard } from "@/components/ImportSourceCard";

describe("ImportSourceCard paste", () => {
  it("counts characters and sends the text", async () => {
    const onExtract = vi.fn();
    render(<ImportSourceCard kind="paste" onExtract={onExtract} />);
    expect(screen.getByText("0 / 100,000 characters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Text to import"), "Ister has two moons.");
    expect(screen.getByText("20 / 100,000 characters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Extract entries" }));
    expect(onExtract).toHaveBeenCalledWith({ text: "Ister has two moons." });
  });

  it("keeps Extract entries disabled for whitespace only", async () => {
    render(<ImportSourceCard kind="paste" onExtract={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Text to import"), "   ");
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });

  it("blocks text over the cap with the exact copy", async () => {
    render(<ImportSourceCard kind="paste" onExtract={vi.fn()} />);
    await userEvent.click(screen.getByLabelText("Text to import"));
    await userEvent.paste("a".repeat(100_001));
    expect(screen.getByText("100,001 / 100,000 characters")).toBeInTheDocument();
    expect(
      screen.getByText("Over the 100,000-character limit for one import. Split it into smaller imports."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });
});

describe("ImportSourceCard upload", () => {
  it("offers only .md and .txt files in the file picker", () => {
    render(<ImportSourceCard kind="upload" onExtract={vi.fn()} />);
    expect(screen.getByLabelText("Choose a file")).toHaveAttribute("accept", ".md,.txt");
  });

  it("rejects a pdf", async () => {
    render(<ImportSourceCard kind="upload" onExtract={vi.fn()} />);
    // The picker's filter can be switched to all files, so the check still runs on the name.
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText("Choose a file"), new File(["x"], "notes.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("Only .md and .txt files can be imported.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });

  it("reads a .md file and sends it with its filename", async () => {
    const onExtract = vi.fn();
    render(<ImportSourceCard kind="upload" onExtract={onExtract} />);
    await userEvent.upload(
      screen.getByLabelText("Choose a file"),
      new File(["# Ister\nTwo moons."], "ister.md", { type: "text/markdown" }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Extract entries" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Extract entries" }));
    expect(onExtract).toHaveBeenCalledWith({ text: "# Ister\nTwo moons.", filename: "ister.md" });
  });

  it("keeps Extract entries disabled for an empty file", async () => {
    render(<ImportSourceCard kind="upload" onExtract={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Choose a file"), new File(["  \n"], "empty.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });
});

describe("ImportSourceCard wiki", () => {
  it("says Coming soon and has no button", () => {
    render(<ImportSourceCard kind="wiki" />);
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
