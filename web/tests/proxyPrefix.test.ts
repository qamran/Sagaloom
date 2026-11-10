import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PROXY_BASE } from "@/lib/api";

// The proxy prefix lives in two languages: PROXY_BASE here, PROXY_PREFIX in the API's export
// tool (the download link it hands the agent). This test is where the two must agree.
const WEB = join(__dirname, "..");

describe("proxy prefix", () => {
  it("the API's export tool uses PROXY_BASE", () => {
    const source = readFileSync(join(WEB, "..", "api", "sagaloom", "tools", "export.py"), "utf8");
    const match = source.match(/^PROXY_PREFIX = "([^"]*)"$/m);
    expect(match?.[1]).toBe(PROXY_BASE);
  });

  it("the proxy route is served at PROXY_BASE", () => {
    expect(existsSync(join(WEB, "app", ...PROXY_BASE.split("/").filter(Boolean), "[...path]", "route.ts"))).toBe(true);
  });
});
