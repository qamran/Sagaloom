import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Toggle } from "@/components/Toggle";

describe("Toggle", () => {
  it("is a switch with a track and knob, its state in words, and a pointer cursor", async () => {
    const onChange = vi.fn();
    render(<Toggle label="export_world" on onChange={onChange} />);
    const sw = screen.getByRole("switch", { name: "export_world" });
    expect(sw).toBeChecked();
    expect(sw).toHaveTextContent("On");
    expect(sw).toHaveClass("cursor-pointer");
    expect(sw.querySelector("[data-knob]")).not.toBeNull();
    await userEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("cannot be flipped while disabled, and says so with its cursor", async () => {
    const onChange = vi.fn();
    render(<Toggle label="export_world" on disabled onChange={onChange} />);
    const sw = screen.getByRole("switch", { name: "export_world" });
    expect(sw).toBeDisabled();
    expect(sw).toHaveClass("cursor-not-allowed");
    await userEvent.click(sw);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows Off for an off switch", () => {
    render(<Toggle label="Input guard" on={false} onChange={() => {}} />);
    expect(screen.getByRole("switch", { name: "Input guard" })).toHaveTextContent("Off");
  });
});
