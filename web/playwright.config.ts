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

// Config is loaded again inside each worker; wipe the data only once, in the main process.
if (process.env.TEST_WORKER_INDEX === undefined) {
  fs.rmSync(DATA_DIR, { recursive: true, force: true });
}

export default defineConfig({
  testDir: "./e2e",
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
  webServer: [
    {
      command: `uv run uvicorn sagaloom.web.app:app --port ${API_PORT}`,
      cwd: "../api",
      env: { DATA_DIR, WEB_ORIGIN: `http://localhost:${WEB_PORT}` },
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 180_000,
      reuseExistingServer: false,
    },
    {
      command: `pnpm dev --port ${WEB_PORT}`,
      env: { API_URL: `http://localhost:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}/canon`,
      timeout: 180_000,
      reuseExistingServer: false,
    },
  ],
});
