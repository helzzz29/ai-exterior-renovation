import { expect, test } from "@playwright/test";
import { canvasImage, createProject, register, sampleDataUrl, uploadPhoto, waitForParts } from "./helpers";

test.describe("photo upload checks", () => {
  test.beforeEach(async ({ page }) => {
    await register(page, "upload");
    await createProject(page, "Upload checks");
  });

  const problem = (page: import("@playwright/test").Page) =>
    page.getByRole("alert").filter({ hasText: "This photo won't work" });

  test("a tiny image gets a friendly 'too small' card and the uploader stays open", async ({ page }) => {
    const tiny = await canvasImage(page, { width: 320, height: 240, kind: "flat", name: "tiny.jpg" });
    await uploadPhoto(page, tiny);
    await expect(problem(page)).toBeVisible();
    await expect(problem(page)).toContainText("This photo is too small to measure.");
    await expect(page.getByRole("button", { name: "Choose a photo" })).toBeVisible();
    await expect(page.getByText("Tips for a good photo")).toBeVisible();
  });

  test("a blurry image gets a friendly 'too blurry' card", async ({ page }) => {
    const blurry = await canvasImage(page, { width: 1600, height: 1200, kind: "gradient", name: "blurry.jpg" });
    await uploadPhoto(page, blurry);
    await expect(problem(page)).toBeVisible();
    await expect(problem(page)).toContainText("This photo is too blurry to measure. Hold the phone steady");
  });

  test("a file that is not a photo is refused before upload", async ({ page }) => {
    await uploadPhoto(page, { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
    // the title names the cause (the file type), not the photo
    const typeProblem = page.getByRole("alert").filter({ hasText: "That file type won't work" });
    await expect(typeProblem).toContainText("Please choose a JPEG, PNG or WebP photo.");
  });

  test("a broken JPEG gets a friendly message, not a crash", async ({ page }) => {
    await uploadPhoto(page, { name: "broken.jpg", mimeType: "image/jpeg", buffer: Buffer.from("not really a jpeg") });
    await expect(problem(page)).toBeVisible();
    const text = await problem(page).innerText();
    expect(text).not.toMatch(/Traceback|Exception|500|undefined|null/);
  });

  test("G1 warning: a small but usable photo shows the warning card, 'Use this photo' continues", async ({ page }) => {
    const small = await canvasImage(page, {
      width: 1000,
      height: 700,
      kind: "photo",
      name: "small-house.jpg",
      photoUrl: sampleDataUrl(),
    });
    await uploadPhoto(page, small);
    await expect(page.getByText("Your photo can be used, with one thing to know")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("This photo is a bit small, so sizes may be less accurate.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload a better photo" })).toBeVisible();
    await page.getByRole("button", { name: "Use this photo" }).click();
    await waitForParts(page);
  });

  test("G1 warning: 'Upload a better photo' goes back to the uploader", async ({ page }) => {
    const small = await canvasImage(page, {
      width: 1000,
      height: 700,
      kind: "photo",
      name: "small-house.jpg",
      photoUrl: sampleDataUrl(),
    });
    await uploadPhoto(page, small);
    await expect(page.getByText("Your photo can be used, with one thing to know")).toBeVisible({ timeout: 90_000 });
    await page.getByRole("button", { name: "Upload a better photo" }).click();
    await expect(page.getByRole("button", { name: "Choose a photo" })).toBeVisible();
    await uploadPhoto(page);
    await waitForParts(page);
  });
});
