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

  it("an empty file says so", async () => {
    render(<ImportSourceCard kind="upload" onExtract={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Choose a file"), new File(["  \n"], "empty.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That file has no text to import.");
  });

  it("the same file can be chosen again after a rejection", async () => {
    render(<ImportSourceCard kind="upload" onExtract={vi.fn()} />);
    const input = screen.getByLabelText("Choose a file") as HTMLInputElement;
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(input, new File(["x"], "notes.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // The browser fires no change event when the same file is picked again unless the value was cleared.
    expect(input.value).toBe("");
  });
});

describe("ImportSourceCard wiki", () => {
  const urls = (n: number) => Array.from({ length: n }, (_, i) => `https://en.wikipedia.org/wiki/Page_${i}`).join("\n");
  const paste = async (text: string) => {
    await userEvent.click(screen.getByLabelText("Page URLs, one per line"));
    await userEvent.paste(text);
  };

  it("names Wikipedia and Fandom and says the licence is read from the wiki", () => {
    render(<ImportSourceCard kind="wiki" onExtract={vi.fn()} />);
    expect(screen.getByText(/Wikipedia or Fandom/)).toBeInTheDocument();
    expect(screen.getByText(/licence is read from the wiki/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });

  it("refuses 11 lines with the count copy and disables the button", async () => {
    render(<ImportSourceCard kind="wiki" onExtract={vi.fn()} />);
    await paste(urls(11));
    expect(screen.getByRole("alert")).toHaveTextContent("Paste 1 to 10 page URLs, one per line.");
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });

  it("explains a Category: URL", async () => {
    render(<ImportSourceCard kind="wiki" onExtract={vi.fn()} />);
    await paste("https://en.wikipedia.org/wiki/Category:Elves");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Only article pages can be imported, not category, file or special pages: https://en.wikipedia.org/wiki/Category:Elves",
    );
    expect(screen.getByRole("button", { name: "Extract entries" })).toBeDisabled();
  });

  it("sends three good lines as a wiki body", async () => {
    const onExtract = vi.fn();
    render(<ImportSourceCard kind="wiki" onExtract={onExtract} />);
    const three = [
      "https://en.wikipedia.org/wiki/Rivendell",
      "https://en.wikipedia.org/wiki/Gandalf",
      "https://en.wikipedia.org/wiki/Shire_(Middle-earth)",
    ];
    await paste(three.join("\n"));
    expect(screen.queryByRole("alert")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Extract entries" }));
    expect(onExtract).toHaveBeenCalledWith({ kind: "wiki", urls: three });
  });

  it("gives the Paste card the id the Review links point at", () => {
    render(<ImportSourceCard kind="paste" onExtract={vi.fn()} />);
    expect(screen.getByRole("region", { name: "Paste text" })).toHaveAttribute("id", "paste");
  });
});
