/** The Clerk test user the exit demo signs in as (e2e/README.md), read from the environment, which
 * playwright.config.ts fills from web/.env.local. Shared by the config, the global setup and the spec. */
export const NO_TEST_USER =
  "Skipping the exit demo: no Clerk test user. Set E2E_CLERK_USER_EMAIL and E2E_CLERK_USER_PASSWORD in web/.env.local (see web/e2e/README.md).";

/** The email (trimmed) and the password (as given), or null when either is unset or blank. */
export function testUser(): { email: string; password: string } | null {
  const email = process.env.E2E_CLERK_USER_EMAIL?.trim() ?? "";
  const password = process.env.E2E_CLERK_USER_PASSWORD ?? "";
  return email && password.trim() ? { email, password } : null;
}
