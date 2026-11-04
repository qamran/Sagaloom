import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FeatureMap } from "@/components/FeatureMap";
import { ProvidersPanel } from "@/components/ProvidersPanel";
import { putModel } from "@/lib/api";
import type { FeatureCardData, ModelsPayload, ProviderStatus } from "@/lib/types";

vi.mock("@/lib/api", () => ({ putModel: vi.fn() }));

const cards: FeatureCardData[] = [
  { id: "agentic_rag", title: "Agentic RAG", brief_ref: "Hard 1", req_ids: ["R7", "R11.1"], status: "live",
    detail: "The agent decides when to search canon.", try_href: "/chat?prompt=How%20many%20moons" },
  { id: "multi_provider", title: "Multi-model, multi-provider", brief_ref: "Medium 7", req_ids: ["R11.G8"],
    status: "configured", detail: "Gemini key present, demo only.", try_href: "#models" },
  { id: "external_tools", title: "External data tools", brief_ref: "Medium 3, Hard 5", req_ids: ["R11.4"],
    status: "off", detail: "Arrives in M2.", try_href: null },
];

describe("FeatureMap", () => {
  it("renders status badges and Try it links", () => {
    render(<FeatureMap features={cards} />);
    const rag = screen.getByRole("article", { name: "Agentic RAG" });
    expect(within(rag).getByText("Live")).toBeInTheDocument();
    expect(within(rag).getByText("R7, R11.1")).toBeInTheDocument();
    expect(within(rag).getByRole("link", { name: /Try it/ })).toHaveAttribute(
      "href",
      "/chat?prompt=How%20many%20moons",
    );
    expect(within(screen.getByRole("article", { name: /Multi-model/ })).getByText("Configured")).toBeInTheDocument();
    const off = screen.getByRole("article", { name: "External data tools" });
    expect(within(off).getByText("Off")).toBeInTheDocument();
    expect(within(off).queryByRole("link")).toBeNull();
    expect(screen.getByText("1 Live")).toBeInTheDocument();
    expect(screen.getByText("1 Configured")).toBeInTheDocument();
    expect(screen.getByText("1 Off")).toBeInTheDocument();
  });
});

const models: ModelsPayload = {
  mapping: {
    agent: "openai/gpt-6-luna",
    judge: "openai/gpt-6-luna",
    extractor: "openai/gpt-6-luna",
    guard: "openai/gpt-6-luna",
  },
  allowed: [
    { id: "openai/gpt-6-luna", price_in: 0.1, price_out: 0.5 },
    { id: "openai/gpt-6.1-terra", price_in: 1.5, price_out: 9 },
  ],
};
const providers: ProviderStatus[] = [
  { name: "OpenRouter", key_set: true, role: "all real calls, provider pinned", notice: null,
    models: [{ id: "openai/text-embedding-3-small", role: "embeddings", price_in: 0.02, price_out: 0 }] },
  { name: "Gemini", key_set: true, role: "demo only, not used for real calls", models: [],
    notice: "Free-tier Gemini prompts may be used by Google." },
];

describe("ProvidersPanel", () => {
  it("role dropdown lists only allowlisted models and calls PUT on change", async () => {
    vi.mocked(putModel).mockResolvedValue({
      ...models,
      mapping: { ...models.mapping, judge: "openai/gpt-6.1-terra" },
    });
    render(<ProvidersPanel providers={providers} models={models} />);
    const select = screen.getByLabelText("Model for the contradiction judge") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["openai/gpt-6-luna", "openai/gpt-6.1-terra"]);

    await userEvent.selectOptions(select, "openai/gpt-6.1-terra");
    expect(putModel).toHaveBeenCalledWith("judge", "openai/gpt-6.1-terra");
    expect(select.value).toBe("openai/gpt-6.1-terra");
    expect(await screen.findByText("1.50 · 9.00")).toBeInTheDocument();
    expect(screen.getByText(/demo only, not used for real calls/)).toBeInTheDocument();
    expect(screen.getByText(/Free-tier Gemini/)).toBeInTheDocument();
  });

  it("shows the error and keeps the old choice when the API refuses", async () => {
    vi.mocked(putModel).mockRejectedValue(new Error("422"));
    render(<ProvidersPanel providers={providers} models={models} />);
    const select = screen.getByLabelText("Model for the chat agent") as HTMLSelectElement;
    await userEvent.selectOptions(select, "openai/gpt-6.1-terra");
    expect(await screen.findByRole("alert")).toHaveTextContent(/not saved/i);
    expect(select.value).toBe("openai/gpt-6-luna");
  });
});
