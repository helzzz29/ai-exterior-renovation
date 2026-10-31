// Change-after-approval scenarios driven through the UI.
import { expect, type Page, test } from "@playwright/test";
import {
  acceptLook,
  createLook,
  editFirstRate,
  finalise,
  journeyToMaterials,
  partChips,
  pickMaterial,
  removeSelectedPart,
  waitForLook,
  waitForSaved,
  waitForTotalsSettled,
} from "./helpers";

const STALE_ESTIMATE = "Your estimate changed after you finalised it. Review it and finalise it again to update the report.";
const STALE_LOOK = "Your materials changed after we created your new look. Create it again to use it in the report.";

/** Accepted design + finalised estimate; ends on the cost screen with the report unlocked. */
async function readyForReport(page: Page, name: string): Promise<string> {
  const projectId = await journeyToMaterials(page, name);
  await createLook(page);
  await acceptLook(page);
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await page.waitForURL(/\/cost\?design=/);
  await finalise(page);
  await expect(page.getByRole("button", { name: "Download report" })).toBeEnabled();
  return projectId;
}

function checklist(page: Page) {
  return page.getByTestId("report-checklist");
}

test("prices changed after finalising: estimate needs update and report is locked", async ({ page }) => {
  await readyForReport(page, "Rates after finalise");

  await editFirstRate(page, 1.5);
  await expect(page.getByTestId("needs-update")).toContainText(STALE_ESTIMATE);
  await expect(page.getByTestId("finalised")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download report" })).toBeDisabled();
  await expect(checklist(page)).toContainText("Finalise your estimate");

  // the design is unaffected by a price change
  await expect(page.getByTestId("needs-update")).not.toContainText("new look");

  // finalising again unlocks the report with a new version number
  await finalise(page);
  await expect(page.getByTestId("finalised")).toContainText("version 2");
  await expect(page.getByTestId("needs-update")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download report" })).toBeEnabled();
});

test("materials changed after accepting: design and estimate need update, report locked", async ({ page }) => {
  await readyForReport(page, "Materials after accept");

  await page.getByRole("link", { name: /Choose materials/ }).first().click();
  await page.waitForURL(/\/materials/);
  await pickMaterial(page, /^Main wall/, 1);
  await waitForSaved(page);

  await expect(page.getByTestId("needs-update")).toContainText(STALE_LOOK);

  await page.getByRole("link", { name: /Cost & report/ }).click();
  await page.waitForURL(/\/cost/);
  await waitForTotalsSettled(page);
  await expect(page.getByRole("button", { name: "Download report" })).toBeDisabled();
  // the checklist names the real cause: the accepted look is out of date
  await expect(checklist(page)).toContainText("Create your new look again, then accept it");
  await expect(checklist(page)).toContainText("Finalise your estimate again");
  // estimate changed with the materials, so it is not final any more
  await expect(page.getByRole("button", { name: "Finalise estimate" })).toBeVisible();

  // the look screen must not offer the stale picture as accepted
  await page.getByRole("link", { name: /Your new look/ }).click();
  await page.waitForURL(/\/look/);
  await expect(page.getByText("You chose this look. It will go in your report.")).toHaveCount(0);

  // recreate + accept + finalise -> unlocked again
  await page.getByRole("link", { name: /Choose materials/ }).first().click();
  await createLook(page);
  await acceptLook(page);
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await finalise(page);
  await expect(page.getByRole("button", { name: "Download report" })).toBeEnabled();
});

test("redo with a note: new image must be accepted again, costs unaffected", async ({ page }) => {
  await readyForReport(page, "Redo with note");
  const total = await page.getByTestId("grand-total").innerText();

  await page.getByRole("link", { name: /Your new look/ }).click();
  await page.waitForURL(/\/look/);
  await page.getByRole("button", { name: "Change something" }).click();
  await page.getByLabel("Tell us what to change, e.g. a warmer stone colour").fill("a warmer wall colour");
  await page.getByRole("button", { name: "Create it again" }).click();
  await waitForLook(page);
  await expect(page.getByText("Your note: “a warmer wall colour”")).toBeVisible();
  await expect(page.getByRole("button", { name: "I like it" })).toBeVisible();

  await page.getByRole("link", { name: /Cost & report/ }).click();
  await page.waitForURL(/\/cost/);
  await waitForTotalsSettled(page);
  await expect(page.getByTestId("grand-total")).toHaveText(total);
  await expect(page.getByTestId("finalised")).toBeVisible(); // estimate unaffected
  await expect(page.getByRole("button", { name: "Download report" })).toBeDisabled();
  await expect(checklist(page)).toContainText("Accept your new look");

  await page.getByRole("link", { name: "Accept your new look" }).click();
  await acceptLook(page);
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await expect(page.getByRole("button", { name: "Download report" })).toBeEnabled();
});

test("size reference changed: estimate needs update, design unaffected", async ({ page }) => {
  await readyForReport(page, "Size after finalise");
  const total = await page.getByTestId("grand-total").innerText();

  await page.getByRole("link", { name: /Size check/ }).click();
  await page.waitForURL(/\/size/);
  await page.getByRole("button", { name: "Change the measurement" }).click();
  await page.getByLabel("Width of the front of the house (ft)").fill("55");
  await page.getByRole("button", { name: "Use this measurement" }).click();
  await page.waitForURL(/\/materials/);

  await page.getByRole("link", { name: /Cost & report/ }).click();
  await page.waitForURL(/\/cost/);
  await waitForTotalsSettled(page);
  await expect(page.getByTestId("grand-total")).not.toHaveText(total);
  await expect(page.getByTestId("needs-update")).toContainText(STALE_ESTIMATE);
  await expect(page.getByRole("button", { name: "Download report" })).toBeDisabled();
  // design stays accepted
  await expect(checklist(page)).toBeVisible();
  await expect(checklist(page).locator("li").first().locator("svg.text-success")).toHaveCount(1);
});

test("parts changed after confirming: parts screen reopens, designs need update", async ({ page }) => {
  await readyForReport(page, "Parts after finalise");

  await page.getByRole("link", { name: /Parts of your house/ }).click();
  await page.waitForURL(/\/parts/);
  await expect(page.getByText("You're changing parts you already confirmed.", { exact: false })).toBeVisible();

  // remove one window
  await (await partChips(page, "Window")).first().click();
  await removeSelectedPart(page);
  await expect(page.getByText("Changes saved")).toBeVisible();

  await page.getByRole("button", { name: "Looks good, continue" }).click();
  await page.waitForURL(/\/(size|materials)/);
  if (/\/size/.test(page.url())) {
    const lookRight = page.getByRole("button", { name: "Yes, looks right" });
    if (await lookRight.isVisible().catch(() => false)) await lookRight.click();
    else {
      const go = page.getByRole("link", { name: "Continue to materials" });
      if (await go.isVisible().catch(() => false)) await go.click();
    }
    await page.waitForURL(/\/materials/);
  }
  await expect(page.getByTestId("needs-update")).toBeVisible();

  await page.getByRole("link", { name: /Cost & report/ }).click();
  await page.waitForURL(/\/cost/);
  await waitForTotalsSettled(page);
  await expect(page.getByRole("button", { name: "Download report" })).toBeDisabled();
});
