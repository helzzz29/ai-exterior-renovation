import { statSync, readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import {
  acceptLook,
  answerAllChecks,
  approvePartsAndSize,
  createLook,
  createProject,
  editFirstRate,
  finalise,
  pickMaterial,
  register,
  settleDesigns,
  uploadPhoto,
  waitForParts,
  waitForSaved,
} from "./helpers";

test("full journey: photo to downloaded PDF report", async ({ page }) => {
  await register(page, "happy");
  await createProject(page, "Happy path house");

  // Step 1: photo + analysis progress
  await uploadPhoto(page);
  await waitForParts(page);

  // G2: answer every "Please check" card and any proposed box
  const counter = page.getByTestId("check-counter");
  const answered = await answerAllChecks(page);
  expect(answered.checked + answered.proposed, "the fake provider marks at least one part as unsure").toBeGreaterThan(0);
  await expect(counter).toHaveText("Everything is checked");
  await expect(page.getByText("Thanks, everything is checked.")).toBeVisible();

  // G3: whichever variant appears
  const variant = await approvePartsAndSize(page);
  test.info().annotations.push({ type: "size-check", description: variant });

  // Step 4: materials for walls and pillars
  await expect(page.getByRole("heading", { name: "Choose materials" })).toBeVisible();
  await settleDesigns(page);
  await pickMaterial(page, /^Main wall/);
  await pickMaterial(page, /^Pillar/);
  await waitForSaved(page);

  // G4: new look
  await createLook(page);
  await acceptLook(page);

  // G5: cost screen
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await page.waitForURL(/\/cost\?design=/);
  await expect(page.getByRole("heading", { name: "Cost & report" })).toBeVisible();
  await expect(page.getByTestId("estimate-kind")).toHaveText("Measured estimate");
  await expect(page.getByTestId("total-range")).toContainText(/About ₹[\d,]+ \(likely between ₹[\d,]+ and ₹[\d,]+\)/);

  // "How was this calculated?" expands the steps
  await page.getByRole("button", { name: "How was this calculated?" }).first().click();
  await expect(page.getByTestId("derivation").first()).toBeVisible();

  const download = page.getByRole("button", { name: "Download report" });
  await expect(download).toBeDisabled();

  const [before, after] = await editFirstRate(page);
  expect(after).not.toBe(before);
  await expect(page.getByText("Changed", { exact: true }).first()).toBeVisible();

  await finalise(page);
  await expect(page.getByTestId("finalised")).toContainText(/Estimate finalised/);

  // report
  // one button: it builds the report and the PDF downloads by itself
  await expect(download).toBeEnabled();
  const [file] = await Promise.all([page.waitForEvent("download", { timeout: 90_000 }), download.click()]);
  await expect(page.getByRole("button", { name: /Open the report/ })).toHaveCount(0);
  const filePath = test.info().outputPath("report.pdf");
  await file.saveAs(filePath);
  expect(file.suggestedFilename()).toMatch(/renovation report v\d+\.pdf$/);
  const size = statSync(filePath).size;
  expect(size, "report PDF size in bytes").toBeGreaterThan(10 * 1024);
  expect(readFileSync(filePath).subarray(0, 5).toString()).toBe("%PDF-");
});
