import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// The M1 exit demo, end to end, against the real seed and real models.
const SEED = path.resolve(__dirname, "../../seed/velmar/scripted_proposals.json");
const scripted: { name: string; draft: { body: string } }[] = JSON.parse(fs.readFileSync(SEED, "utf-8"));
const SORN_TEXT = scripted.find((s) => s.name === "captain_sorn")!.draft.body;
// A bare statement is answered rather than proposed, and the agent picks its own fact keys, so the
// demo asks for the change and names the fact (see docs/review-notes.md, error scenarios).
const THREE_MOONS =
  "Update the Sky of Velmar entry and set its fact Moons to Three: Velmar has three moons that rise together at the solstice.";

const card = (page: Page, title: string) => page.getByRole("region", { name: `Review proposal: ${title}` });
const log = (page: Page) => page.getByRole("log", { name: "Conversation" });

async function send(page: Page, text: string) {
  const composer = page.getByLabel("Message Sagaloom");
  await expect(composer).toBeEnabled();
  await composer.fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("M1 exit demo", async ({ page }) => {
  // 1. Canon: Sky of Velmar shows its Moons fact.
  await page.goto("/canon");
  await page.getByRole("link", { name: /Sky of Velmar/ }).first().click();
  await expect(page.getByRole("region", { name: "Facts" }).or(page.getByLabel("Facts"))).toContainText("Moons");

  // 2. Ask: the answer cites an entry ID.
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[^/]+/);
  await send(page, "How many moons does Velmar have?");
  await expect(log(page)).toContainText(/ent_0007|ent_0012/);

  // 3. A contradiction: a Conflict card citing ent_0012. Reject it.
  await send(page, THREE_MOONS);
  const conflict = card(page, "Sky of Velmar");
  await expect(conflict).toBeVisible();
  await expect(conflict.getByRole("list", { name: "Check result" }).getByText("Conflict", { exact: true })).toBeVisible();
  await expect(conflict.locator('a[href="/canon/ent_0012"]').first()).toBeVisible();
  await conflict.getByRole("button", { name: "Reject" }).click();
  await expect(log(page)).toContainText(/rejected by the author/);

  // 4. A clean proposal: no Conflict badge. Approve it, then find it in Canon.
  await send(page, `Add this character to canon. ${SORN_TEXT}`);
  const sorn = card(page, "Captain Sorn");
  await expect(sorn).toBeVisible();
  await expect(sorn.getByRole("list", { name: "Check result" }).getByText("Conflict", { exact: true })).toHaveCount(0);
  await sorn.getByRole("button", { name: /^Approve/ }).click();
  await expect(log(page)).toContainText(/committed as ent_\d{4}/);
  await page.getByRole("link", { name: "Canon", exact: true }).click();
  await expect(page.getByRole("link", { name: /Captain Sorn/ }).first()).toBeVisible();

  // 5. The pending card survives a reload (R5.5).
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[^/]+/);
  await send(page, THREE_MOONS);
  await expect(card(page, "Sky of Velmar")).toBeVisible();
  await page.reload();
  await expect(card(page, "Sky of Velmar")).toBeVisible();

  // 6. Save as myth: the card is re-checked and its Moons fact carries a myth badge.
  await card(page, "Sky of Velmar").getByRole("button", { name: "Save as myth" }).click();
  const mythCard = card(page, "Sky of Velmar");
  const moons = mythCard
    .getByRole("region", { name: "Drafted facts" })
    .locator("xpath=.//div[div[normalize-space()='Moons']]");
  await expect(moons.getByText("myth", { exact: true })).toBeVisible();
  await mythCard.getByRole("button", { name: /^Approve/ }).click();
  await expect(log(page)).toContainText(/committed as ent_0007/);

  // 7. Under the hood: the judge's request holds the retrieved Ister entry inside its wrapper.
  await page.getByRole("button", { name: "Under the hood" }).click();
  const drawer = page.getByRole("complementary", { name: "Under the hood" });
  // The drawer shows one turn at a time; pick the turn that ran the contradiction check.
  const judge = drawer.getByRole("button", { name: /Contradiction judge/ }).first();
  const turns = page.getByLabel("Turn shown in Under the hood");
  const options = await turns.locator("option").count();
  for (let i = 0; i < options; i++) {
    await turns.selectOption({ index: i });
    if (await judge.waitFor({ timeout: 5_000 }).then(() => true, () => false)) break;
  }
  await judge.click();
  const request = drawer.getByRole("region", { name: "Request" }).last(); // the judge call, opened after the agent call
  await expect(request).toContainText("untrusted_data");
  await expect(request.getByTestId("untrusted").filter({ hasText: "Ister" }).first()).toBeVisible();

  // ...and Studio's Feature map shows the four core features as Live (R20.3, R20.5).
  await page.goto("/studio");
  for (const title of ["Agentic RAG", "Human-in-the-loop", "Memory", "Token usage and cost"]) {
    await expect(page.getByRole("article", { name: title }).getByText("Live", { exact: true })).toBeVisible();
  }
});
