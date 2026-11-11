import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

// The demo runs against real LLM calls, on its own ports and a throwaway data directory, so it
// never touches a dev server or the real data/ folder. The shared secret is the one already in
// api/.env and web/.env.local; the proxy adds it, the browser never sees it.
const API_PORT = 8100;
const WEB_PORT = 3100;
const DATA_DIR = path.join(os.tmpdir(), "sagaloom-e2e-data");
// The e2e web server builds into its own folder: Next 16 locks `.next/dev` for one `next dev`, so
// a second one in this folder (next to the author's `pnpm dev`) would exit. next.config.ts reads it.
const E2E_DIST_DIR = ".next-e2e";

// Nothing else loads web/.env.local into this process: clerkSetup() (e2e/global-setup.ts) needs the
// Clerk keys, the spec the test user (E2E_CLERK_USER_EMAIL / E2E_CLERK_USER_PASSWORD). A variable
// already set in the real environment wins.
const ENV_LOCAL = path.join(__dirname, ".env.local");
if (fs.existsSync(ENV_LOCAL)) process.loadEnvFile(ENV_LOCAL);
const E2E_EMAIL = process.env.E2E_CLERK_USER_EMAIL?.trim() ?? "";
const hasTestUser = E2E_EMAIL !== "" && (process.env.E2E_CLERK_USER_PASSWORD ?? "").trim() !== "";

// Config is loaded again inside each worker; wipe the data only once, in the main process. The
// e2e server's data cache (the home page preview) goes too, since Next keeps it across restarts.
if (process.env.TEST_WORKER_INDEX === undefined) {
  fs.rmSync(DATA_DIR, { recursive: true, force: true });
  fs.rmSync(path.join(__dirname, E2E_DIST_DIR, "dev", "cache", "fetch-cache"), { recursive: true, force: true });
}

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 20 * 60_000,
  expect: { timeout: 180_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    actionTimeout: 120_000,
    trace: "retain-on-failure",
  },
  // Without the Clerk test user the spec skips (see e2e/README.md), so no server is started.
  webServer: hasTestUser
    ? [
        {
          // Seed the wiki cache first (R-W3-10): the fan-wiki step's pages and licence come from the committed
          // fixtures, so that step sends no request to Wikipedia.
          command: `uv run python scripts/seed_wiki_cache.py "${DATA_DIR}" && uv run uvicorn sagaloom.web.app:app --port ${API_PORT}`,
          cwd: "../api",
          // CLERK_ISSUER and CLERK_SECRET_KEY come from the root .env and api/.env, as for the dev API. The
          // test user is the admin: the demo switches admin-only settings (the input guard, the tools).
          env: { DATA_DIR, WEB_ORIGIN: `http://localhost:${WEB_PORT}`, ADMIN_EMAIL: E2E_EMAIL },
          url: `http://localhost:${API_PORT}/api/health`,
          timeout: 180_000,
          reuseExistingServer: false,
        },
        {
          command: `pnpm dev --port ${WEB_PORT}`,
          env: { API_URL: `http://localhost:${API_PORT}`, NEXT_DIST_DIR: E2E_DIST_DIR },
          // A public page: every app page answers 307 to sign-in now.
          url: `http://localhost:${WEB_PORT}/sign-in`,
          timeout: 180_000,
          reuseExistingServer: false,
        },
      ]
    : [],
});
