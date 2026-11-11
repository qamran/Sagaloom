import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
      // Next resolves `server-only` itself; under vitest (a server-side test) it is an empty module.
      "server-only": fileURLToPath(new URL("./node_modules/next/dist/compiled/server-only/empty.js", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    testTimeout: 15_000,
    maxWorkers: 2,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    // Type assertions (expectTypeOf) fail the run only when vitest type-checks them.
    typecheck: { enabled: true, include: ["tests/**/*.test-d.ts"] },
  },
});
