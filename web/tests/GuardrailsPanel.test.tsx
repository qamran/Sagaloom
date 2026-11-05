import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GuardrailsPanel } from "@/components/GuardrailsPanel";
import { getGuardLog, putSettings } from "@/lib/api";
import type { SettingsPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({ putSettings: vi.fn(), getGuardLog: vi.fn() }));

const payload: SettingsPayload = {
  settings: { agent_temperature: 0, agent_max_tokens: null, agent_system_prompt: null, guard_enabled: true },
  defaults: { agent_system_prompt: "x" },
  guard_policy: "You are the input guard.",
};

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <GuardrailsPanel payload={payload} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(putSettings).mockReset().mockResolvedValue(payload);
  vi.mocked(getGuardLog)
    .mockReset()
    .mockResolvedValue([
      { thread_id: "t_abc", started_at: "2026-01-01T00:00:00", model: "m", verdict: "injection", reason: "override" },
      { thread_id: "t_def", started_at: "2026-01-01T00:00:01", model: "m", verdict: "safe", reason: "fine" },
    ]);
});

describe("GuardrailsPanel", () => {
  it("renders the policy read-only", () => {
    setup();
    const pre = screen.getByText("You are the input guard.");
    expect(pre.tagName).toBe("PRE");
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("toggles the guard with a switch", async () => {
    setup();
    const sw = screen.getByRole("switch", { name: /input guard/i });
    expect(sw).toBeChecked();
    await userEvent.click(sw);
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ guard_enabled: false }));
  });

  it("lists recent verdicts with a badge and the thread id", async () => {
    setup();
    const row = (await screen.findByText("t_abc")).closest("li") as HTMLElement;
    expect(within(row).getByText("injection")).toBeInTheDocument();
    expect(within(row).getByText("override")).toBeInTheDocument();
    expect(screen.getByText("t_def")).toBeInTheDocument();
  });
});
