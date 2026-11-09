import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UnderTheHood } from "@/components/UnderTheHood";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
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
  it("links to the agent graph for the thread", () => {
    render(<UnderTheHood turn={turn} threadId="t 1" onClose={() => {}} />);
    expect(screen.getByRole("link", { name: "See it on the agent graph" })).toHaveAttribute(
      "href",
      "/studio?thread=t%201#agent-graph",
    );
  });

  it("says prompts are recorded as sent and secrets are hidden on screen", () => {
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    expect(
      screen.getByText(
        "Prompts are recorded exactly as sent; secret facts are hidden on screen until you choose Show. Copy as JSON copies the full record.",
      ),
    ).toBeInTheDocument();
  });

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
    const router = { ...turn, calls: [{ ...turn.calls[0], role: "router" }] };
    const second = render(<UnderTheHood turn={router} onClose={() => {}} />);
    expect(screen.getByText("Router")).toBeInTheDocument();
    second.unmount();
    render(<UnderTheHood turn={turn} onClose={() => {}} />);
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  describe("secrets", () => {
    const SECRET_BLOCK =
      '<untrusted_data source="ent_0003">\nTitle: Mayor Elsbeth Varr\n- Age: 54 [canon]\n- Sings with the Ashen Choir: Yes, at every full Ister [secret]\n</untrusted_data>';
    const HIDDEN = "Hidden: this call saw secret facts. Choose Show secrets to read it.";
    const secretTurn: TurnView = {
      ...turn,
      calls: [
        {
          ...turn.calls[0],
          role: "judge",
          messages: [{ role: "user", content: `# Proposal\n${SECRET_BLOCK}` }],
          response: { ...turn.calls[0].response!, content: "The Mayor sings with the Ashen Choir." },
        },
      ],
    };

    async function tabs() {
      const user = userEvent.setup();
      const request = screen.getByRole("region", { name: "Request" });
      const req = request.textContent ?? "";
      await user.click(screen.getByRole("button", { name: "Response" }));
      const res = screen.getByRole("region", { name: "Response" }).textContent ?? "";
      await user.click(screen.getByRole("button", { name: "Raw JSON" }));
      const raw = screen.getByTestId("raw-json").textContent ?? "";
      await user.click(screen.getByRole("button", { name: "Request" }));
      return { req, res, raw };
    }

    it("masks secret lines in the request, and the response and raw JSON, while hidden", async () => {
      render(<UnderTheHood turn={secretTurn} worldId="w1" onClose={() => {}} />);
      const request = screen.getByRole("region", { name: "Request" });
      const wrapped = within(request).getByTestId("untrusted");
      expect(wrapped).toHaveTextContent("[secret fact hidden]");
      expect(wrapped).toHaveTextContent("- Age: 54 [canon]");
      expect(wrapped).toHaveTextContent("<untrusted_data");
      const { req, res, raw } = await tabs();
      expect(req).not.toContain("Ashen Choir");
      expect(res).toBe(HIDDEN);
      expect(raw).toBe(HIDDEN);
    });

    it("shows all three tabs verbatim after the drawer's Show secrets, which is the world's toggle", async () => {
      render(<UnderTheHood turn={secretTurn} worldId="w1" onClose={() => {}} />);
      const toggle = screen.getByRole("button", { name: "Show secrets" });
      expect(toggle).toHaveAttribute("aria-pressed", "false");
      await userEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-pressed", "true");
      expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w1"))).toBe("true");
      const { req, res, raw } = await tabs();
      expect(req).toContain("Sings with the Ashen Choir: Yes, at every full Ister [secret]");
      expect(req).not.toContain("[secret fact hidden]");
      expect(res).toContain("The Mayor sings with the Ashen Choir.");
      expect(raw).toContain("Yes, at every full Ister");
      expect(raw).toContain("The Mayor sings with the Ashen Choir.");
    });

    it("follows its own world's toggle, not another world's", () => {
      sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
      render(<UnderTheHood turn={secretTurn} worldId="w2" onClose={() => {}} />);
      expect(screen.getByRole("region", { name: "Request" })).not.toHaveTextContent("Ashen Choir");
    });

    it("copies the verbatim record whether secrets are hidden or shown", async () => {
      const user = userEvent.setup();
      const writeText = vi.fn(async () => {});
      stubClipboard(writeText);
      render(<UnderTheHood turn={secretTurn} worldId="w1" onClose={() => {}} />);
      await user.click(screen.getByRole("button", { name: "Copy as JSON" }));
      await user.click(screen.getByRole("button", { name: "Copy turn as JSON" }));
      await user.click(screen.getByRole("button", { name: "Show secrets" }));
      await user.click(screen.getByRole("button", { name: "Copy as JSON" }));
      const copies = writeText.mock.calls.map((c) => (c as unknown as [string])[0]);
      expect(copies).toHaveLength(3);
      for (const c of copies) {
        expect(c).toContain("Yes, at every full Ister [secret]");
        expect(c).not.toContain("[secret fact hidden]");
      }
      expect(copies[1]).toContain("The Mayor sings with the Ashen Choir.");
    });

    it("shows the response of a call with no secrets while hidden", async () => {
      render(<UnderTheHood turn={turn} worldId="w1" onClose={() => {}} />);
      await userEvent.click(screen.getByRole("button", { name: "Response" }));
      expect(screen.getByText("No conflict.")).toBeInTheDocument();
      expect(screen.queryByText(HIDDEN)).toBeNull();
    });
  });
});
