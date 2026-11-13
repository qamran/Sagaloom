import { QueryClient, QueryClientProvider, QueryObserver } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GuardrailsPanel } from "@/components/GuardrailsPanel";
import { getGuardLog, putSettings } from "@/lib/api";
import type { SettingsPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({ putSettings: vi.fn(), getGuardLog: vi.fn() }));

const payload: SettingsPayload = {
  settings: { agent_temperature: 0, agent_max_tokens: null, agent_system_prompt: null, guard_enabled: true, enabled_tools: null, monthly_budget_usd: 1 },
  defaults: { agent_system_prompt: "x" },
  guard_policy: "You are the input guard.",
};

function setup(qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
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
    expect(sw).toHaveAttribute("aria-checked", "true");
    vi.mocked(putSettings).mockResolvedValue({ ...payload, settings: { ...payload.settings, guard_enabled: false } });
    await userEvent.click(sw);
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ guard_enabled: false }));
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
  });

  it("saving does not refetch the model list", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const settings = vi.fn().mockResolvedValue(payload);
    const models = vi.fn().mockResolvedValue([]);
    await qc.fetchQuery({ queryKey: ["settings"], queryFn: settings });
    await qc.fetchQuery({ queryKey: ["settings", "models"], queryFn: models });
    const observe = (queryKey: string[], queryFn: () => Promise<unknown>) =>
      new QueryObserver(qc, { queryKey, queryFn, staleTime: Infinity }).subscribe(() => {});
    const off = [observe(["settings"], settings), observe(["settings", "models"], models)];
    try {
      setup(qc);
      await userEvent.click(screen.getByRole("switch", { name: /input guard/i }));
      await waitFor(() => expect(settings).toHaveBeenCalledTimes(2));
      expect(models).toHaveBeenCalledTimes(1);
    } finally {
      off.forEach((f) => f());
    }
  });

  it("lists recent verdicts with a badge and the thread id", async () => {
    setup();
    const row = (await screen.findByText("t_abc")).closest("li") as HTMLElement;
    expect(within(row).getByText("injection")).toBeInTheDocument();
    expect(within(row).getByText("override")).toBeInTheDocument();
    expect(screen.getByText("t_def")).toBeInTheDocument();
  });

  it("styles a failed guard call's error verdict", async () => {
    vi.mocked(getGuardLog).mockResolvedValue([
      { thread_id: "t_err", started_at: "2026-01-01T00:00:02", model: "m", verdict: "error", reason: "" },
    ]);
    setup();
    const row = (await screen.findByText("t_err")).closest("li") as HTMLElement;
    const badge = within(row).getByText("error");
    expect(badge.className).not.toContain("undefined");
    expect(badge.className).toContain("text-failed");
  });
});

describe("GuardrailsPanel read-only", () => {
  it("disables the guard switch and says why for a non-admin", async () => {
    vi.mocked(getGuardLog).mockResolvedValue([]);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GuardrailsPanel payload={payload} readOnly />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("switch", { name: "Input guard" })).toBeDisabled();
    expect(
      screen.getByText("Only the admin can change developer settings."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(getGuardLog).toHaveBeenCalledWith(20, "mine", undefined),
    );
  });

  it("lists only the given world's verdicts", async () => {
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <GuardrailsPanel payload={payload} worldId="w2" />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(getGuardLog).toHaveBeenCalledWith(20, "mine", "w2"),
    );
  });
});
