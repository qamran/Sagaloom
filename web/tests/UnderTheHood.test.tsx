import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UnderTheHood } from "@/components/UnderTheHood";
import type { TurnView } from "@/lib/turns";

const WRAPPED = '<untrusted_data source="ent_0012">Ister, the red moon.</untrusted_data>';

const turn: TurnView = {
  key: "live-1",
  label: "Turn 1",
  nodes: [
    { name: "agent", ms: 800, phase: "done" },
    { name: "tools", ms: 300, phase: "done" },
    { name: "approval_gate", ms: null, phase: "paused" },
  ],
  tools: [{ name: "search_canon", args: { query: "moons" }, summary: "4 hits" }],
  calls: [
    {
      id: "c1",
      provider: "openrouter",
      model: "openai/gpt-6-luna",
      params: { temperature: 0 },
      messages: [
        { role: "user", content: `PROPOSED Moons: Three\n${WRAPPED}` },
        { role: "system", content: "You are the continuity judge." },
      ],
      tools: [{ type: "function", function: { name: "search_canon", parameters: { SCHEMA_MARKER: 1 } } }],
      response: {
        content: "No conflict.",
        tool_calls: [],
        prompt_tokens: 3120,
        completion_tokens: 210,
        cost_usd: 0.0004,
        latency_ms: 800,
      },
    },
  ],
};

function stubClipboard(writeText: (t: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

afterEach(() => vi.restoreAllMocks());

describe("UnderTheHood", () => {
  it("shows system prompt, highlights untrusted_data, collapses tool schemas", () => {
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    const request = screen.getByRole("region", { name: /Request/ });
    const roles = within(request)
      .getAllByTestId("message-role")
      .map((n) => n.textContent);
    expect(roles).toEqual(["system", "user"]); // system first, even when it arrived later
    expect(within(request).getByText(/continuity judge/)).toBeInTheDocument();
    const wrapped = within(request).getByTestId("untrusted");
    expect(wrapped).toHaveTextContent("Ister, the red moon.");
    expect(wrapped).toHaveTextContent("<untrusted_data");
    const schemas = within(request).getByText(/tool schemas/i).closest("details") as HTMLDetailsElement;
    expect(schemas.open).toBe(false);
    expect(screen.getByText("agent")).toBeInTheDocument();
    expect(screen.getByText("paused")).toBeInTheDocument();
    expect(screen.getAllByText(/search_canon/).length).toBeGreaterThan(0);
    expect(screen.getByText(/3,120 → 210 tok/)).toBeInTheDocument();
  });

  it("copy-as-JSON copies the request", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => {});
    stubClipboard(writeText);
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Copy as JSON" }));
    expect(writeText).toHaveBeenCalledTimes(1);
    const copied = JSON.parse((writeText.mock.calls[0] as unknown as [string])[0]);
    expect(copied.model).toBe("openai/gpt-6-luna");
    expect(copied.request.messages).toHaveLength(2);
    expect(copied.request.messages[0].role).toBe("user");
    expect(JSON.stringify(copied.request.tools)).toContain("SCHEMA_MARKER");
  });

  it("does not throw when the clipboard is unavailable", async () => {
    const user = userEvent.setup();
    stubClipboard(async () => {
      throw new Error("denied");
    });
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Copy as JSON" }));
    expect(await screen.findByText(/could not copy/i)).toBeInTheDocument();
  });

  it("switches between Request, Response and Raw JSON", async () => {
    const user = userEvent.setup();
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Response" }));
    expect(screen.getByText("No conflict.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Raw JSON" }));
    expect(screen.getByTestId("raw-json")).toHaveTextContent('"model": "openai/gpt-6-luna"');
  });

  it("labels a call from its role, and falls back when the role is missing", () => {
    const withRole = { ...turn, calls: [{ ...turn.calls[0], role: "judge" }] };
    const { unmount } = render(<UnderTheHood turn={withRole} onClose={() => {}} />);
    expect(screen.getByText("Contradiction judge")).toBeInTheDocument();
    unmount();
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });
});
