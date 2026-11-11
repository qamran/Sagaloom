import { clerkSetup } from "@clerk/testing/playwright";
import { NO_TEST_USER, testUser } from "./testUser";

/** Fetches a Clerk testing token once for the run (it lets the browser past Clerk's bot protection).
 * Skipped without the test user, as the spec is: then nothing here talks to Clerk. */
export default async function globalSetup() {
  if (!testUser()) {
    // The list reporter does not print a skip reason, so say it here too.
    console.log(NO_TEST_USER);
    return;
  }
  // playwright.config.ts has already loaded web/.env.local.
  await clerkSetup({ dotenv: false });
}
