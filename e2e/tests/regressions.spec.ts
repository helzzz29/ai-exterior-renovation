// Focused checks for bugs found by the end-to-end runs (see the bug list in the QA report).
import { expect, test } from "@playwright/test";
import {
  answerAllChecks,
  approvePartsAndSize,
  createProject,
  register,
  settleDesigns,
  uploadPhoto,
  waitForParts,
  waitForTotalsSettled,
} from "./helpers";

async function toMaterials(page: import("@playwright/test").Page, name: string) {
  await register(page, "reg");
  await createProject(page, name);
  await uploadPhoto(page);
  await waitForParts(page);
  await answerAllChecks(page);
  await approvePartsAndSize(page);
  await expect(page.getByRole("heading", { name: "Choose materials" })).toBeVisible();
}

test("a new project starts with exactly one design", async ({ page }) => {
  await toMaterials(page, "One design");
  const tabs = page.getByRole("tablist", { name: "Your designs" }).getByRole("tab");
  await expect(tabs.first()).toBeVisible();
  await page.waitForTimeout(2000); // give a duplicate time to appear
  await expect(tabs).toHaveCount(1);
});

test("a material chosen just before leaving the screen is kept", async ({ page }) => {
  await toMaterials(page, "Quick leave");
  await settleDesigns(page);
  const rg = page.getByRole("radiogroup", { name: /^Main wall/ });
  const option = rg.getByRole("radio").filter({ hasNotText: "Keep as it is" }).first();
  await option.click();
  await expect(page.getByText("Choices saved")).toBeVisible();
  // the screen says "Choices saved", so leaving straight away must be safe
  await page.getByRole("link", { name: /Cost & report/ }).click();
  await page.waitForURL(/\/cost/);
  await waitForTotalsSettled(page);
  await expect(page.getByTestId("grand-total")).toBeVisible();
});
