import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "@/components/Composer";
import type { Named } from "@/lib/mentions";

const entries: Named[] = [
  { id: "ent_0003", title: "Mayor Elsbeth Varr", type: "character", aliases: [], status: "canon" },
  { id: "ent_0001", title: "Velmar", type: "place", aliases: [], status: "canon" },
  { id: "ent_0019", title: "The Choir Ledger", type: "item", aliases: [], status: "secret" },
];

function setup(props: Partial<React.ComponentProps<typeof Composer>> = {}) {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} entries={entries} showSecrets={false} {...props} />);
  return { onSend, box: screen.getByRole("combobox") as HTMLTextAreaElement };
}

describe("Composer @ autocomplete", () => {
  it("opens a listbox of matching entries on @el", async () => {
    const { box } = setup();
    expect(box).toHaveAttribute("aria-expanded", "false");
    await userEvent.type(box, "ask @el");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Mayor Elsbeth Varr/ })).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-expanded", "true");
    expect(box).not.toHaveAttribute("aria-activedescendant");
    await userEvent.keyboard("{ArrowDown}");
    expect(box.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[0].id);
  });

  it("inserts the pick on ArrowDown then Enter, without sending", async () => {
    const { box, onSend } = setup();
    await userEvent.type(box, "hi @el");
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(box.value).toBe("hi Mayor Elsbeth Varr ");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
    await userEvent.keyboard("is here{Enter}");
    expect(onSend).toHaveBeenCalledWith("hi Mayor Elsbeth Varr is here");
  });

  it("closes on Escape and does not send on Enter while open", async () => {
    const { box, onSend } = setup();
    await userEvent.type(box, "@el");
    await userEvent.keyboard("{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(box).toHaveAttribute("aria-expanded", "false");
  });

  it("does not open for an @ inside a word", async () => {
    const { box } = setup();
    await userEvent.type(box, "me@el");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("never offers a hidden secret entry", async () => {
    const { box } = setup();
    await userEvent.type(box, "@choir");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("offers a secret entry when secrets are shown", async () => {
    const { box } = setup({ showSecrets: true });
    await userEvent.type(box, "@choir");
    expect(screen.getByRole("option", { name: /The Choir Ledger/ })).toBeInTheDocument();
  });

  it("still sends on Enter and keeps Shift+Enter for a new line", async () => {
    const { box, onSend } = setup();
    await userEvent.type(box, "one{Shift>}{Enter}{/Shift}two{Enter}");
    expect(onSend).toHaveBeenCalledWith("one\ntwo");
  });
});

describe("Composer over budget", () => {
  const detail = "You've used this month's AI budget ($1.00). It resets on 2026-12-01.";

  it("shows the budget message in place of the input", () => {
    render(<Composer onSend={vi.fn()} blocked={detail} />);
    expect(screen.getByText(detail)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });
});
