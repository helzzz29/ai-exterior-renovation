// axe scan (WCAG 2.1 A/AA) of every screen. Serious/critical violations fail (softly, so all
// screens are scanned in one run); every violation is printed and attached to the report.
import { expect, test } from "@playwright/test";
import {
  acceptLook,
  answerAllChecks,
  canvasImage,
  createProject,
  finalise,
  pickMaterial,
  sampleDataUrl,
  scanA11y,
  settleDesigns,
  uniqueEmail,
  uploadPhoto,
  waitForLook,
  waitForParts,
  waitForSaved,
  PASSWORD,
} from "./helpers";

test("accessibility of every screen", async ({ page }, testInfo) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await scanA11y(page, testInfo, "login");

  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click(); // shows an error next to each empty field
  await expect(page.getByRole("alert").first()).toBeVisible();
  await scanA11y(page, testInfo, "register-with-error");
  await page.getByLabel("Email").fill(uniqueEmail("a11y"));
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "No projects yet" })).toBeVisible();
  await scanA11y(page, testInfo, "projects-empty");

  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "Start a new project" })).toBeVisible();
  await scanA11y(page, testInfo, "create-project");
  await createProject(page, "Accessibility house");
  await scanA11y(page, testInfo, "photo-uploader");

  // upload problem card
  const tiny = await canvasImage(page, { width: 320, height: 240, kind: "flat", name: "tiny.jpg" });
  await uploadPhoto(page, tiny);
  await expect(page.getByText("This photo won't work")).toBeVisible();
  await scanA11y(page, testInfo, "photo-problem");

  // G1 warning card
  const small = await canvasImage(page, { width: 1000, height: 700, kind: "photo", name: "s.jpg", photoUrl: sampleDataUrl() });
  await uploadPhoto(page, small);
  await expect(page.getByText("Your photo can be used, with one thing to know")).toBeVisible({ timeout: 90_000 });
  await scanA11y(page, testInfo, "photo-warning");
  await page.getByRole("button", { name: "Upload a better photo" }).click();
  await uploadPhoto(page);

  // G2 parts, with the "Please check" card open
  await waitForParts(page);
  await scanA11y(page, testInfo, "parts");
  const chip = page.getByRole("button", { name: /Please check/ }).first();
  if (await chip.isVisible()) {
    await chip.click();
    await expect(page.getByTestId("check-card")).toBeVisible();
    await scanA11y(page, testInfo, "parts-check-card");
  }
  await answerAllChecks(page);
  await page.getByRole("button", { name: "Looks good, continue" }).click();

  // G3 size check
  await page.waitForURL(/\/(size|materials)/);
  if (/\/size/.test(page.url())) {
    await expect(page.getByRole("heading", { name: "Size check", exact: true })).toBeVisible();
    await expect(page.locator("[aria-busy=true]")).toHaveCount(0);
    await scanA11y(page, testInfo, "size-check");
    const enter = page.getByRole("button", { name: "Enter a measurement" });
    if (await enter.isVisible()) {
      await enter.click();
      await scanA11y(page, testInfo, "size-check-measurement-form");
    }
    await page.getByLabel("Width of the front of the house (ft)").fill("32");
    await page.getByRole("button", { name: "Use this measurement" }).click();
  }

  // Step 4 materials
  await page.waitForURL(/\/materials/);
  await settleDesigns(page);
  await pickMaterial(page, /^Main wall/);
  await pickMaterial(page, /^Pillar/);
  await waitForSaved(page);
  await scanA11y(page, testInfo, "materials");

  // G4 new look (scan the waiting screen if we catch it, then the result)
  await page.getByRole("button", { name: "Create my new look" }).click();
  await page.waitForURL(/\/look/);
  const creating = page.getByText("Creating your new look…");
  if (await creating.isVisible().catch(() => false)) await scanA11y(page, testInfo, "look-creating");
  await waitForLook(page);
  await scanA11y(page, testInfo, "look");
  await page.getByRole("button", { name: "Change something" }).click();
  await scanA11y(page, testInfo, "look-change-something");
  await page.getByRole("button", { name: "Cancel" }).click();
  await acceptLook(page);

  // G5 cost & report
  await page.getByRole("link", { name: "Continue to cost & report" }).click();
  await page.waitForURL(/\/cost/);
  await expect(page.getByTestId("grand-total")).toBeVisible();
  await page.getByRole("button", { name: "How was this calculated?" }).first().click();
  await scanA11y(page, testInfo, "cost");
  await finalise(page);
  await Promise.all([
    page.waitForEvent("download", { timeout: 90_000 }),
    page.getByRole("button", { name: "Download report" }).click(),
  ]);
  await expect(page.getByRole("button", { name: "Download report" })).toBeEnabled();
  await scanA11y(page, testInfo, "cost-report-ready");

  // trace panel ("How we worked this out")
  const trace = page.getByRole("button", { name: /How we worked this out/ });
  if (await trace.isVisible().catch(() => false)) {
    await trace.click();
    await scanA11y(page, testInfo, "trace-panel");
  }

  await page.goto("/");
  await expect(page.getByText("Accessibility house")).toBeVisible();
  await scanA11y(page, testInfo, "projects-list");

  await page.goto("/no-such-page");
  await scanA11y(page, testInfo, "not-found");
});
