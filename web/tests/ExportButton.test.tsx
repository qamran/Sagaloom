import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExportButton } from "@/components/ExportButton";

describe("ExportButton", () => {
  it("links to the export and toggles exclude_secrets with the checkbox", async () => {
    render(<ExportButton worldId="w_1" />);
    const link = screen.getByRole("link", { name: "Download as Markdown" });
    expect(link).toHaveAttribute("href", "/api/proxy/worlds/w_1/export?format=md");
    expect(link).toHaveAttribute("download");

    await userEvent.click(screen.getByRole("checkbox", { name: "Leave out secrets" }));
    expect(link).toHaveAttribute("href", "/api/proxy/worlds/w_1/export?format=md&exclude_secrets=true");

    await userEvent.click(screen.getByRole("checkbox", { name: "Leave out secrets" }));
    expect(link).toHaveAttribute("href", "/api/proxy/worlds/w_1/export?format=md");
  });
});
