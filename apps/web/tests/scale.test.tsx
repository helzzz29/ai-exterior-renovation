import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { expectPlainLanguage, location, renderApp, seed } from "./helpers";

describe("Step 3: Measure up", () => {
  it("medium: highlights the door, explains it and confirms with one click", async () => {
    const { projectId } = await seed("scale");
    const { user } = renderApp(`/projects/${projectId}/size`);
    expect(await screen.findByText("Does this look right?")).toBeInTheDocument();
    expect(screen.getByTestId("reference-box")).toBeInTheDocument();
    expect(screen.getByTestId("scale-explanation")).toHaveTextContent(/We used your main door as a guide \(standard height 7 ft\)/);
    expectPlainLanguage();
    await user.click(screen.getByRole("button", { name: "Yes, looks right" }));
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/materials`));
    expect(db.projects[0].scale_confirmed).toBe(true);
  });

  it("medium: can switch to entering a measurement", async () => {
    const { projectId } = await seed("scale");
    const { user } = renderApp(`/projects/${projectId}/size`);
    await user.click(await screen.findByRole("button", { name: "Enter a measurement" }));
    await user.type(screen.getByLabelText("Width of the front of the house (ft)"), "30");
    await user.click(screen.getByRole("button", { name: "Use this measurement" }));
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/materials`));
    expect(db.projects[0].scaleSet?.method).toBe("user_measurement");
    expect(db.projects[0].scaleSet?.facade_width_ft).toBeCloseTo(30, 5);
  });

  it("low: a measurement is required", async () => {
    const { projectId } = await seed("scale", { removeDoor: true });
    const { user } = renderApp(`/projects/${projectId}/size`);
    expect(await screen.findByText("We need one measurement")).toBeInTheDocument();
    expect(screen.getByText(/Enter the width of your house, or draw a line/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes, looks right" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use this measurement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please enter a length above zero.");
    await user.click(screen.getByRole("tab", { name: "Draw a line on the photo" }));
    await user.click(screen.getByRole("button", { name: "Use this measurement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Tap two points on the photo first.");
  });

  it("low: drawing has a keyboard-friendly alternative", async () => {
    const { projectId } = await seed("scale", { removeDoor: true });
    const { user } = renderApp(`/projects/${projectId}/size`);
    await user.click(await screen.findByRole("tab", { name: "Draw a line on the photo" }));
    await user.click(screen.getByRole("button", { name: /Enter the width of the house instead/ }));
    await waitFor(() => expect(screen.getByLabelText("Width of the front of the house (ft)")).toHaveFocus());
  });

  it("low: accepts the width of the house", async () => {
    const { projectId } = await seed("scale", { removeDoor: true });
    const { user } = renderApp(`/projects/${projectId}/size`);
    await user.type(await screen.findByLabelText("Width of the front of the house (ft)"), "28");
    await user.click(screen.getByRole("button", { name: "Use this measurement" }));
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/materials`));
    expect(db.projects[0].stage).toBe("designing");
  });

  it("high: a measurement from step 1 skips the screen", async () => {
    const { projectId } = await seed("regions", { measurements: { facade_width_ft: 31 } });
    const p = db.projects[0];
    // Pretend the size was not confirmed yet, so the screen confirms it itself.
    p.regions_approved = true;
    p.stage = "scale_review";
    p.scale_confirmed = false;
    p.regions.forEach((r) => {
      r.checked = true;
      r.proposed = false;
    });
    renderApp(`/projects/${projectId}/size`);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/materials`));
  });

  it("after confirming, shows the size and a way to change it", async () => {
    const { projectId } = await seed("designing");
    renderApp(`/projects/${projectId}/size`);
    expect(await screen.findByText("Measure up done")).toBeInTheDocument();
    expect(screen.getByText(/Your house is about 23 ft wide/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change the measurement" })).toBeInTheDocument();
  });
});
