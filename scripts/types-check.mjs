// Regenerate the API types into a temp dir and fail if they differ from the committed files.
import { execSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const tmp = mkdtempSync(join(tmpdir(), "sagaloom-types-"));
const json = join(tmp, "openapi.json");
const ts = join(tmp, "api-types.gen.ts");
const read = (p) => readFileSync(p, "utf8").replace(/\r\n/g, "\n");

try {
  execSync(`uv run python scripts/export_openapi.py "${json}"`, { cwd: join(root, "api"), stdio: "inherit" });
  execSync(`pnpm exec openapi-typescript --default-non-nullable=false "${json}" -o "${ts}"`, { cwd: join(root, "web"), stdio: "inherit" });
  const stale =
    read(json) !== read(join(root, "web/lib/openapi.json")) ||
    read(ts) !== read(join(root, "web/lib/api-types.gen.ts"));
  if (stale) {
    console.error("Generated API types are stale: run pnpm types:gen");
    process.exitCode = 1;
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
