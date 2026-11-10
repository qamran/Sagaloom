// Regenerate the API types into a temp dir and fail if they differ from the committed files.
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { COMMITTED_JSON, COMMITTED_TS, generate } from "./types-gen.mjs";

const tmp = mkdtempSync(join(tmpdir(), "sagaloom-types-"));
const json = join(tmp, "openapi.json");
const ts = join(tmp, "api-types.gen.ts");
const read = (p) => readFileSync(p, "utf8").replace(/\r\n/g, "\n");

try {
  generate(json, ts);
  const stale = read(json) !== read(COMMITTED_JSON) || read(ts) !== read(COMMITTED_TS);
  if (stale) {
    console.error("Generated API types are stale: run pnpm types:gen");
    process.exitCode = 1;
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
