import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CourseChip } from "@/components/CourseChip";
import { FeatureMap } from "@/components/FeatureMap";
import { Header } from "@/components/Header";
import type { FeatureCardData } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/chat", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ worlds: [], world: null, threadId: null, setWorldId: vi.fn(), startWorld: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({ getThread: vi.fn(), getReviewThreads: vi.fn(async () => []), getMe: vi.fn(async () => undefined) }));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => ({ isLoaded: true, isSignedIn: true }), UserButton: () => null }));

const page = () => (
  <QueryClientProvider client={new QueryClient()}>
    <Header />
    <CourseChip card="human_in_the_loop" label="Human-in-the-loop · interrupt()" />
  </QueryClientProvider>
);

afterEach(() => vi.restoreAllMocks());

describe("CourseChip", () => {
  it("links to the Studio feature card", () => {
    render(page());
    expect(screen.getByRole("link", { name: "Course note: Human-in-the-loop · interrupt()" })).toHaveAttribute(
      "href",
      "/studio?card=human_in_the_loop#feature-map",
    );
  });

  it("hides every chip when the header toggle is off, and remembers the choice", async () => {
    const { unmount } = render(page());
    const toggle = screen.getByRole("button", { name: "Course notes" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("link", { name: /Course note/ })).toBeNull();
    unmount();
    render(page());
    expect(screen.getByRole("button", { name: "Course notes" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("link", { name: /Course note/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Course notes" }));
    expect(screen.getByRole("link", { name: /Course note/ })).toBeInTheDocument();
  });

  it("still shows chips when localStorage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(page());
    expect(screen.getByRole("link", { name: /Course note/ })).toBeInTheDocument();
  });
});

describe("course notes storage", () => {
  it("course notes follow the last write while storage fails", async () => {
    render(page());
    const toggle = screen.getByRole("button", { name: "Course notes" });
    if (toggle.getAttribute("aria-pressed") === "true") await userEvent.click(toggle);
    expect(localStorage.getItem("sagaloom.courseNotes")).toBe("false");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /Course note/ })).toBeInTheDocument();
    // A working write clears the module's memory copy, so later tests read storage again.
    vi.mocked(Storage.prototype.setItem).mockRestore();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(localStorage.getItem("sagaloom.courseNotes")).toBe("false");
  });
});

describe("FeatureMap highlight", () => {
  it("marks the highlighted card", () => {
    const cards: FeatureCardData[] = ["memory", "agentic_rag"].map((id) => ({
      id, title: id, brief_ref: "x", req_ids: [], status: "live", detail: "d", try_href: null,
    }));
    render(<FeatureMap features={cards} highlight="memory" />);
    expect(screen.getByRole("article", { name: "memory" })).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByRole("article", { name: "agentic_rag" })).not.toHaveAttribute("data-highlighted");
  });
});
