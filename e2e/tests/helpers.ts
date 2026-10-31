import { appendFileSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
export const SAMPLES = path.resolve(here, "..", "..", "samples");
export const HOUSE = path.join(SAMPLES, "house-02.jpg");

/** Every axe finding of a run, one JSON object per line (git-ignored). */
export const A11Y_LOG = path.resolve(here, "..", "a11y-report.jsonl");

export const PASSWORD = "e2e-password-123";

export function uniqueEmail(tag: string): string {
  return `e2e-${tag}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** Register a fresh user through the UI; ends on "My projects". */
export async function register(page: Page, tag = "user"): Promise<string> {
  const email = uniqueEmail(tag);
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "My projects" })).toBeVisible();
  return email;
}

export interface ProjectOptions {
  width?: string;
}

/** Create a project; ends on the photo step. Returns the project id. */
export async function createProject(page: Page, name: string, opts: ProjectOptions = {}): Promise<string> {
  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "Start a new project" })).toBeVisible();
  await page.getByLabel("Project name").fill(name);
  if (opts.width) await page.getByLabel("Width of the front of the house (ft)").fill(opts.width);
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/[^/]+\/photo$/);
  await expect(page.getByRole("heading", { name: "Your photo" })).toBeVisible();
  return page.url().split("/projects/")[1].split("/")[0];
}

export type UploadFile = string | { name: string; mimeType: string; buffer: Buffer };

export async function uploadPhoto(page: Page, file: UploadFile = HOUSE): Promise<void> {
  await page.getByTestId("photo-input").setInputFiles(file);
}

/** Wait until analysis has finished and the parts screen is open. */
export async function waitForParts(page: Page): Promise<void> {
  await page.waitForURL(/\/parts(\?|$)/, { timeout: 90_000 });
  await expect(page.getByRole("heading", { name: "Parts of your house" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "All parts we found" })).toBeVisible();
}

/** Answer every "Please check" card (Yes) and every proposed dashed box (keep / reject alternately). */
/**
 * The individual (already answered) parts of one kind in the parts list. Several parts of the same
 * kind are grouped in one row ("Window · 4"); this opens the row and returns its chips
 * ("Window 1", "Window 2", …, or just "Window" when there is only one).
 */
export async function partChips(page: Page, name: string): Promise<Locator> {
  const group = page.getByRole("button", { name: new RegExp(`^${name} · \\d+$`) });
  if ((await group.count()) > 0 && (await group.getAttribute("aria-expanded")) === "false") {
    await group.click();
  }
  return page.getByRole("button", { name: new RegExp(`^${name}( \\d+)?$`) });
}

export async function answerAllChecks(page: Page): Promise<{ checked: number; proposed: number }> {
  let checked = 0;
  let proposed = 0;
  for (let guard = 0; guard < 30; guard++) {
    const pendingChip = page.getByRole("button", { name: /Please check/ }).first();
    const proposedChip = page.locator("li > button.border-dashed").first();
    if (await pendingChip.isVisible().catch(() => false)) {
      await pendingChip.click();
      const card = page.getByTestId("check-card");
      await expect(card).toBeVisible();
      await expect(card.getByRole("heading", { name: /^Is this an? / })).toBeVisible();
      await card.getByRole("button", { name: "Yes", exact: true }).click();
      checked++;
      continue;
    }
    if (await proposedChip.isVisible().catch(() => false)) {
      await proposedChip.click();
      const card = page.getByTestId("proposed-card");
      await expect(card).toBeVisible();
      await card.getByRole("button", { name: proposed % 2 === 0 ? "Yes, keep it" : "No" }).click();
      proposed++;
      continue;
    }
    break;
  }
  return { checked, proposed };
}

/** Approve parts and handle whichever size-check variant appears; ends on the materials step. */
export async function approvePartsAndSize(page: Page, width = "32"): Promise<"skipped" | "medium" | "low" | "high"> {
  const cont = page.getByRole("button", { name: "Looks good, continue" });
  await expect(cont).toBeEnabled();
  await cont.click();
  await page.waitForURL(/\/(size|materials)(\?|$)/);
  if (/\/materials/.test(page.url())) return "skipped";
  return sizeCheck(page, width);
}

export async function sizeCheck(page: Page, width = "32"): Promise<"medium" | "low" | "high"> {
  await expect(page.getByRole("heading", { name: "Size check", exact: true })).toBeVisible();
  const lookRight = page.getByRole("button", { name: "Yes, looks right" });
  const lowTitle = page.getByText("We need one measurement", { exact: true });
  const highTitle = page.getByText("Thanks, your measurement is all we need");
  await expect(lookRight.or(lowTitle).or(highTitle).first()).toBeVisible();
  let variant: "medium" | "low" | "high";
  if (await lookRight.isVisible()) {
    variant = "medium";
    await expect(page.getByTestId("scale-explanation")).not.toBeEmpty();
    await lookRight.click();
  } else if (await lowTitle.isVisible()) {
    variant = "low";
    await page.getByLabel("Width of the front of the house (ft)").fill(width);
    await page.getByRole("button", { name: "Use this measurement" }).click();
  } else {
    variant = "high";
  }
  await page.waitForURL(/\/materials(\?|$)/);
  return variant;
}

/**
 * On first arrival at the materials screen the app may create a second "Design 1" (known bug,
 * see the bug list). Wait for the list to settle, then select the first design explicitly so the
 * choices and the cost screen refer to the same design. Returns how many designs exist.
 */
export async function settleDesigns(page: Page): Promise<number> {
  const tabs = page.getByRole("tablist", { name: "Your designs" }).getByRole("tab");
  await expect(tabs.first()).toBeVisible();
  await page.waitForTimeout(1500);
  await tabs.first().click();
  await expect(tabs.first()).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/design=/);
  return tabs.count();
}

/**
 * Open one kind of part on the materials screen. Only one kind is open at a time; its header
 * button's name starts with the part's name (e.g. "Pillar 2 parts Kept as it is").
 */
export async function openGroup(page: Page, group: RegExp): Promise<Locator> {
  const header = page.getByRole("button", { name: group }).and(page.locator("[aria-expanded]")).first();
  await expect(header).toBeVisible();
  if ((await header.getAttribute("aria-expanded")) === "false") await header.click();
  const rg = page.getByRole("radiogroup", { name: group });
  await expect(rg).toBeVisible();
  return rg;
}

/** Pick a material (by position among the offered options) for one group of parts. */
export async function pickMaterial(page: Page, group: RegExp, index = 0): Promise<string> {
  const rg = await openGroup(page, group);
  const options = rg.getByRole("radio").filter({ hasNotText: "Keep as it is" });
  await expect(options.first()).toBeVisible();
  const option = options.nth(index);
  const name = (await option.locator("span.font-medium").first().innerText()).trim();
  // wait for the real autosave request: the "Choices saved" text shows before it is sent (bug)
  const saved = page.waitForResponse(
    (r) => /\/api\/designs\/[^/]+\/assignments$/.test(r.url()) && r.request().method() === "PUT" && r.ok(),
  );
  await option.click();
  await expect(option).toHaveAttribute("aria-checked", "true");
  await saved;
  return name;
}

/** "Remove it" on the selected part, then confirm in the dialog that asks first. */
export async function removeSelectedPart(page: Page): Promise<void> {
  await page.getByTestId("selected-card").getByRole("button", { name: "Remove it" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove part" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

export async function waitForSaved(page: Page): Promise<void> {
  await expect(page.getByText("Choices saved")).toBeVisible();
}

/** Click "Create my new look" and wait for the redesign. */
export async function createLook(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "Choose materials" })).toBeVisible();
  await page.getByRole("button", { name: "Create my new look" }).click();
  await page.waitForURL(/\/look\?design=/);
  await waitForLook(page);
}

export async function waitForLook(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "Your new look" })).toBeVisible();
  await expect(page.getByRole("img", { name: "After" })).toBeVisible({ timeout: 90_000 });
}

export async function acceptLook(page: Page): Promise<void> {
  await page.getByRole("button", { name: "I like it" }).click();
  await expect(page.getByText("You chose this look. It will go in your report.")).toBeVisible();
}

export async function grandTotal(page: Page): Promise<string> {
  return (await page.getByTestId("grand-total").innerText()).trim();
}

/** The first material-price input on the cost screen. */
export function firstMaterialRate(page: Page) {
  return page.locator('input[id^="mat-"]').first();
}

export async function waitForTotalsSettled(page: Page): Promise<void> {
  await expect(page.getByText("Updating the totals…")).toHaveCount(0, { timeout: 30_000 });
}

/** Edit the first material price and wait until the total changes; returns [before, after]. */
export async function editFirstRate(page: Page, factor = 2): Promise<[string, string]> {
  await waitForTotalsSettled(page);
  const before = await grandTotal(page);
  const input = firstMaterialRate(page);
  const current = Number(await input.inputValue());
  await input.fill(String(Math.round(current * factor + 1)));
  await expect(input).toHaveAttribute("data-changed", "true");
  await expect(page.getByTestId("grand-total")).not.toHaveText(before, { timeout: 30_000 });
  await waitForTotalsSettled(page);
  return [before, await grandTotal(page)];
}

export async function finalise(page: Page): Promise<void> {
  await waitForTotalsSettled(page);
  const btn = page.getByRole("button", { name: "Finalise estimate" });
  await expect(btn).toBeEnabled();
  await btn.click();
  await expect(page.getByTestId("finalised")).toBeVisible();
}

/** Full journey up to the materials screen with walls + pillars chosen. */
export async function journeyToMaterials(page: Page, name: string): Promise<string> {
  await register(page, "j");
  const projectId = await createProject(page, name);
  await uploadPhoto(page);
  await waitForParts(page);
  await answerAllChecks(page);
  await approvePartsAndSize(page);
  await settleDesigns(page);
  await pickMaterial(page, /^Main wall/);
  await pickMaterial(page, /^Pillar/);
  await waitForSaved(page);
  return projectId;
}

/** Generate an image in the browser (canvas) and return it as an upload payload. */
export async function canvasImage(
  page: Page,
  opts: { width: number; height: number; kind: "flat" | "gradient" | "photo"; name: string; photoUrl?: string },
): Promise<{ name: string; mimeType: string; buffer: Buffer }> {
  const dataUrl = await page.evaluate(async ({ width, height, kind, photoUrl }) => {
    const c = document.createElement("canvas");
    c.width = width;
    c.height = height;
    const ctx = c.getContext("2d")!;
    if (kind === "flat") {
      ctx.fillStyle = "#8a8a8a";
      ctx.fillRect(0, 0, width, height);
    } else if (kind === "gradient") {
      const g = ctx.createLinearGradient(0, 0, width, height);
      g.addColorStop(0, "#9a9a9a");
      g.addColorStop(1, "#a4a4a4");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, width, height);
    } else {
      const img = new Image();
      img.src = photoUrl!;
      await img.decode();
      ctx.drawImage(img, 0, 0, width, height);
    }
    return c.toDataURL("image/jpeg", 0.92);
  }, opts);
  return { name: opts.name, mimeType: "image/jpeg", buffer: Buffer.from(dataUrl.split(",")[1], "base64") };
}

export function sampleDataUrl(file = HOUSE): string {
  return `data:image/jpeg;base64,${readFileSync(file).toString("base64")}`;
}

// ------------------------------------------------------------------ accessibility

export interface A11yFinding {
  screen: string;
  id: string;
  impact: string | null | undefined;
  help: string;
  nodes: number;
  targets: string[];
  details: string[];
}

/**
 * Run axe (WCAG 2.1 A/AA) on the current screen. Every violation is attached to the report;
 * serious and critical ones fail the test (softly, so every screen still gets scanned).
 */
export async function scanA11y(page: Page, testInfo: TestInfo, screen: string): Promise<A11yFinding[]> {
  // let animations and spinners settle so the scan sees the finished screen
  await page.waitForTimeout(300);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const findings: A11yFinding[] = results.violations.map((v) => ({
    screen,
    id: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.length,
    targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
    details: v.nodes.slice(0, 3).map((n) => `${n.html.slice(0, 140)} => ${(n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 220)}`),
  }));
  await testInfo.attach(`axe-${screen}`, {
    body: JSON.stringify(findings, null, 2),
    contentType: "application/json",
  });
  try {
    if (findings.length) appendFileSync(A11Y_LOG, findings.map((f) => JSON.stringify(f)).join("\n") + "\n");
  } catch {
    // the log is a convenience only
  }
  for (const f of findings) {
    console.log(`[axe] ${screen}: ${f.impact} ${f.id} (${f.nodes} nodes) - ${f.help}`);
    for (const d of f.details) console.log(`[axe]    ${d}`);
  }
  const blocking = findings.filter((f) => f.impact === "serious" || f.impact === "critical");
  expect.soft(blocking, `serious/critical accessibility violations on "${screen}"`).toEqual([]);
  return findings;
}
