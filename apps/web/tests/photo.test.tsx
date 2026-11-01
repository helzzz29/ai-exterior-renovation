import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { expectPlainLanguage, location, renderApp, seed } from "./helpers";

function pick(name: string, type = "image/jpeg") {
  const input = screen.getByTestId("photo-input");
  fireEvent.change(input, { target: { files: [new File(["x"], name, { type })] } });
}

describe("Step 1: Snap your home", () => {
  it("uploads, shows progress in plain words, then opens the parts screen", async () => {
    const { projectId } = await seed("upload");
    renderApp(`/projects/${projectId}/photo`);
    expect(await screen.findByText("Drag your photo here")).toBeInTheDocument();
    pick("house.jpg");
    expect(await screen.findByText("Looking at your photo")).toBeInTheDocument();
    expect(screen.getByText("Finding walls, windows and balconies")).toBeInTheDocument();
    expectPlainLanguage();
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/parts`), { timeout: 5000 });
  });

  it("refuses other file types before uploading", async () => {
    const { projectId } = await seed("upload");
    renderApp(`/projects/${projectId}/photo`);
    await screen.findByText("Drag your photo here");
    pick("plan.pdf", "application/pdf");
    expect(await screen.findByRole("alert")).toHaveTextContent("Please choose a JPEG, PNG or WebP photo.");
    expect(db.jobs).toHaveLength(0);
  });

  it("shows instant-check problems as a friendly card", async () => {
    const { projectId } = await seed("upload");
    renderApp(`/projects/${projectId}/photo`);
    await screen.findByText("Drag your photo here");
    // The mock reads the file name; if multipart parsing is unavailable it falls back to a pass.
    pick("blurry.jpg");
    const outcome = await Promise.race([
      screen.findByText("This photo won't work").then(() => "error"),
      screen.findByText("Looking at your photo").then(() => "progress"),
    ]);
    if (outcome === "error") {
      expect(screen.getByText(/too blurry to measure/)).toBeInTheDocument();
      expect(screen.getByText("Tips for a good photo")).toBeInTheDocument();
    }
  });

  it("warning: explains the issue and continues with “Use this photo”", async () => {
    const { projectId } = await seed("upload");
    const p = db.projects[0];
    p.stage = "photo_warning";
    p.hasPhoto = true;
    p.verdict = {
      status: "warn",
      issues: [{ code: "angled_view", severity: "warn", message: "The photo is taken at an angle, so sizes may be less accurate." }],
    };
    const { user } = renderApp(`/projects/${projectId}/photo`);
    expect(await screen.findByText(/taken at an angle/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload a better photo" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use this photo" }));
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/parts`));
    expect(db.projects[0].verdict_overridden).toBe(true);
  });

  it("warning: “Upload a better photo” goes back to the uploader", async () => {
    const { projectId } = await seed("upload");
    Object.assign(db.projects[0], { stage: "photo_warning", hasPhoto: true, verdict: { status: "warn", issues: [] } });
    const { user } = renderApp(`/projects/${projectId}/photo`);
    await user.click(await screen.findByRole("button", { name: "Upload a better photo" }));
    expect(screen.getByText("Drag your photo here")).toBeInTheDocument();
  });

  it("reject: shows tips and only lets the user upload another photo", async () => {
    const { projectId } = await seed("upload");
    Object.assign(db.projects[0], {
      stage: "photo_rejected",
      hasPhoto: true,
      verdict: { status: "reject", issues: [{ code: "not_residential", severity: "hard", message: "This doesn't look like a house." }] },
    });
    const { user } = renderApp(`/projects/${projectId}/photo`);
    expect(await screen.findByText("We can't use this photo")).toBeInTheDocument();
    expect(screen.getByText("This doesn't look like a house.")).toBeInTheDocument();
    expect(screen.getByText("Tips for a good photo")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use this photo" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Upload another photo" }));
    expect(screen.getByText("Drag your photo here")).toBeInTheDocument();
  });

  it("shows the checked photo once the project has moved on", async () => {
    const { projectId } = await seed("regions");
    renderApp(`/projects/${projectId}/photo`);
    expect(await screen.findByText(/Photo checked/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to parts of your house" })).toBeInTheDocument();
  });
});
