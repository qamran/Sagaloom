// Generate the API types: the OpenAPI schema from the API, then the TypeScript types from it.
// Run directly (pnpm types:gen) it writes the committed files; types-check.mjs reuses generate().
import { execSync } from "node:child_process";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(import.meta.dirname, "..");

export const COMMITTED_JSON = join(root, "web/lib/openapi.json");
export const COMMITTED_TS = join(root, "web/lib/api-types.gen.ts");

/** Write the API's OpenAPI schema to jsonPath and the types generated from it to tsPath. */
export function generate(jsonPath, tsPath) {
  execSync(`uv run python scripts/export_openapi.py "${jsonPath}"`, { cwd: join(root, "api"), stdio: "inherit" });
  execSync(`pnpm exec openapi-typescript --default-non-nullable=false "${jsonPath}" -o "${tsPath}"`, {
    cwd: join(root, "web"),
    stdio: "inherit",
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  generate(COMMITTED_JSON, COMMITTED_TS);
}
