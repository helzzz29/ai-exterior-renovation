import { expect, test } from "@playwright/test";
import {
  answerAllChecks,
  approvePartsAndSize,
  createLook,
  createProject,
  pickMaterial,
  register,
  settleDesigns,
  uploadPhoto,
  waitForParts,
  waitForSaved,
} from "./helpers";

test("two users work at the same time and cannot see each other's projects", async ({ browser }) => {
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const a = await ctxA.newPage();
  const b = await ctxB.newPage();

  await Promise.all([register(a, "alice"), register(b, "bob")]);
  const [idA, idB] = await Promise.all([createProject(a, "Alice house"), createProject(b, "Bob house")]);
  expect(idA).not.toBe(idB);

  // both analyses run at the same time
  await Promise.all([uploadPhoto(a), uploadPhoto(b)]);
  await Promise.all([waitForParts(a), waitForParts(b)]);

  const journey = async (page: typeof a) => {
    await answerAllChecks(page);
    await approvePartsAndSize(page);
    await settleDesigns(page);
    await pickMaterial(page, /^Main wall/);
    await waitForSaved(page);
    await createLook(page);
  };
  await Promise.all([journey(a), journey(b)]);

  // each list shows only its own project
  await Promise.all([a.goto("/"), b.goto("/")]);
  await expect(a.getByText("Alice house")).toBeVisible();
  await expect(a.getByText("Bob house")).toHaveCount(0);
  await expect(b.getByText("Bob house")).toBeVisible();
  await expect(b.getByText("Alice house")).toHaveCount(0);

  // B opening A's project URL gets the not-found handling, for every step
  for (const step of ["", "/photo", "/parts", "/cost"]) {
    await b.goto(`/projects/${idA}${step}`);
    await expect(b.getByRole("alert")).toContainText("We couldn't find that project.");
    await expect(b.getByText("Alice house")).toHaveCount(0);
  }

  // A's own session is untouched
  await a.goto(`/projects/${idA}/look`);
  await expect(a.getByRole("heading", { name: "Your new look" })).toBeVisible();

  // a logged-out visitor is sent to log in
  const anon = await browser.newContext();
  const c = await anon.newPage();
  await c.goto(`/projects/${idA}/photo`);
  await expect(c).toHaveURL(/\/login/);
  await expect(c.getByRole("heading", { name: "Welcome back" })).toBeVisible();

  await Promise.all([ctxA.close(), ctxB.close(), anon.close()]);
});
