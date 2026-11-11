import { clerkSetup } from "@clerk/testing/playwright";

/** Fetches a Clerk testing token once for the run (it lets the browser past Clerk's bot protection).
 * Skipped without the test user, as the spec is: then nothing here talks to Clerk. */
export default async function globalSetup() {
  if (!process.env.E2E_CLERK_USER_EMAIL?.trim() || !process.env.E2E_CLERK_USER_PASSWORD?.trim()) {
    // The list reporter does not print a skip reason, so say it here too.
    console.log(
      "Skipping the exit demo: no Clerk test user. Set E2E_CLERK_USER_EMAIL and E2E_CLERK_USER_PASSWORD in web/.env.local (see web/e2e/README.md).",
    );
    return;
  }
  await clerkSetup();
}
