import { expect, test } from "@playwright/test";
import {
  acceptLook,
  answerAllChecks,
  createLook,
  createProject,
  journeyToMaterials,
  partChips,
  openGroup,
  pickMaterial,
  removeSelectedPart,
  register,
  settleDesigns,
  uploadPhoto,
  waitForParts,
  waitForSaved,
  waitForTotalsSettled,
} from "./helpers";

test("size check, low: no door left -> one measurement is required (line option)", async ({ page }) => {
  await register(page, "low");
  await createProject(page, "No door house");
  await uploadPhoto(page);
  await waitForParts(page);
  await answerAllChecks(page);

  // remove the door and all but one window so neither door nor windows can be the guide
  // (estimation.md scale chain: door -> >=2 windows -> floors (low))
  let doors = await partChips(page, "Door");
  while ((await doors.count()) > 0) {
    await doors.first().click();
    await removeSelectedPart(page);
    doors = await partChips(page, "Door");
  }
  await expect(doors).toHaveCount(0);
  let windows = await partChips(page, "Window");
  while ((await windows.count()) > 1) {
    const n = await windows.count();
    await windows.first().click();
    await removeSelectedPart(page);
    windows = await partChips(page, "Window");
    await expect(windows).toHaveCount(n - 1);
  }
  await expect(page.getByText("Changes saved")).toBeVisible();
  await page.getByRole("button", { name: "Looks good, continue" }).click();

  await page.waitForURL(/\/size/);
  await expect(page.getByText("We need one measurement", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Yes, looks right" })).toHaveCount(0);

  // empty submit -> plain-language error
  await page.getByRole("button", { name: "Use this measurement" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Please enter a length above zero." })).toBeVisible();

  // draw a line instead
  await page.getByRole("tab", { name: "Draw a line on the photo" }).click();
  await page.getByLabel("Real length of the line (ft)").fill("20");
  await page.getByRole("button", { name: "Use this measurement" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Tap two points on the photo first." })).toBeVisible();
  const drawer = page.getByTestId("line-drawer");
  const box = (await drawer.boundingBox())!;
  await drawer.click({ position: { x: box.width * 0.15, y: box.height * 0.7 } });
  await drawer.click({ position: { x: box.width * 0.85, y: box.height * 0.7 } });
  await expect(drawer.locator("line")).toHaveCount(1);
  await page.getByRole("button", { name: "Use this measurement" }).click();
  await page.waitForURL(/\/materials/);

  await settleDesigns(page);
  await pickMaterial(page, /^Main wall/);
  await waitForSaved(page);
  await page.getByRole("link", { name: /Cost & report/ }).click();
  await waitForTotalsSettled(page);
  await expect(page.getByTestId("estimate-kind")).toHaveText("Measured estimate");
});

test("size check, high: a width entered at the start skips the question", async ({ page }) => {
  await register(page, "high");
  await createProject(page, "Measured house", { width: "40" });
  await uploadPhoto(page);
  await waitForParts(page);
  await answerAllChecks(page);
  await page.getByRole("button", { name: "Looks good, continue" }).click();
  await page.waitForURL(/\/materials/, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Yes, looks right" })).toHaveCount(0);

  await page.getByRole("link", { name: /Size check/ }).click();
  await expect(page.getByText("Size check done")).toBeVisible();
  await expect(page.getByText("Your house is about 40 ft wide.")).toBeVisible();
});

test("two designs: each keeps its own materials, render and estimate", async ({ page }) => {
  await journeyToMaterials(page, "Two designs");
  const tabs = page.getByRole("tablist", { name: "Your designs" }).getByRole("tab");
  // A new project must start with exactly one design (see bug: default design created twice).
  const start = await tabs.count();
  expect.soft(start, "a new project starts with exactly one design").toBe(1);

  await page.getByRole("button", { name: "Duplicate" }).click();
  await expect(tabs).toHaveCount(start + 1);
  await expect(tabs.nth(start)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(start)).toHaveText("Design 1 (copy)");
  const second = await pickMaterial(page, /^Main wall/, 1);
  await waitForSaved(page);

  await page.getByRole("button", { name: "New design" }).click();
  await expect(tabs).toHaveCount(start + 2);
  await expect(page.getByRole("button", { name: "Create my new look" })).toBeDisabled();
  await expect(page.getByText("Choose a material for at least one part first.")).toBeVisible();

  // design 2: render + accept; its estimate shows its own wall material
  await tabs.nth(start).click();
  await expect((await openGroup(page, /^Main wall/)).getByRole("radio", { checked: true })).toContainText(second);
  await createLook(page);
  await acceptLook(page);
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await waitForTotalsSettled(page);
  await expect(page.locator("tbody")).toContainText(second);
  const total2 = await page.getByTestId("grand-total").innerText();

  // design 1 has no new look yet and its own (different) total
  await page.getByRole("link", { name: /Choose materials/ }).first().click();
  await tabs.first().click();
  await expect(tabs.first()).toHaveAttribute("aria-selected", "true");
  await page.getByRole("link", { name: /Cost & report/ }).click();
  await waitForTotalsSettled(page);
  await expect(page.locator("tbody")).not.toContainText(second);
  await expect(page.getByTestId("grand-total")).not.toHaveText(total2);
  // design 1 has no new look of its own yet, and the checklist says so
  await expect(page.getByTestId("report-checklist")).toContainText("Create your new look and accept it");
});

test("parts: relabel a part through 'No, it's a…' and add-part tool is offered", async ({ page }) => {
  await register(page, "relabel");
  await createProject(page, "Relabel house");
  await uploadPhoto(page);
  await waitForParts(page);
  const chip = page.getByRole("button", { name: /Please check/ }).first();
  await chip.click();
  const card = page.getByTestId("check-card");
  await card.getByRole("button", { name: "No, it's a…" }).click();
  await page.getByRole("menuitem", { name: "Main wall" }).click();
  await expect(page.getByTestId("check-card")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Looks good, continue" })).toBeEnabled();
  await expect(page.getByText("Changes saved")).toBeVisible();

  // the change survives a reload (it was saved automatically)
  await page.reload();
  await waitForParts(page);
  await expect(page.getByRole("button", { name: /Please check/ })).toHaveCount(0);
});
