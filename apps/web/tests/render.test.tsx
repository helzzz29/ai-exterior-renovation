import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { call, expectPlainLanguage, renderApp, seed } from "./helpers";

describe("Step 5: Your new look", () => {
  it("shows progress while the look is being created, then the before/after slider", async () => {
    const { projectId, designId } = await seed("assigned");
    await call("POST", `/api/designs/${designId}/render`, { note: null });
    renderApp(`/projects/${projectId}/look?design=${designId}`);
    expect(await screen.findByText("Creating your new look…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the costs while you wait" })).toBeInTheDocument();
    expectPlainLanguage();
    expect(await screen.findByRole("button", { name: "I like it" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByAltText("Before")).toBeInTheDocument();
    expect(screen.getByAltText("After")).toBeInTheDocument();
  });

  it("“I like it” accepts the design", async () => {
    const { projectId, designId } = await seed("rendered");
    const { user } = renderApp(`/projects/${projectId}/look?design=${designId}`);
    await user.click(await screen.findByRole("button", { name: "I like it" }));
    expect(await screen.findByText("You chose this look. It will go in your report.")).toBeInTheDocument();
    expect(db.renders[0].status).toBe("accepted");
    expect(screen.getByRole("link", { name: "Continue to cost & report" })).toBeInTheDocument();
  });

  it("“Change something” redoes the design with the note", async () => {
    const { projectId, designId } = await seed("rendered");
    const { user } = renderApp(`/projects/${projectId}/look?design=${designId}`);
    await user.click(await screen.findByRole("button", { name: "Change something" }));
    const submit = screen.getByRole("button", { name: "Create it again" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Tell us what to change, e.g. a warmer stone colour"), "a warmer stone colour");
    await user.click(submit);
    expect(await screen.findByText("Creating your new look…")).toBeInTheDocument();
    expect(db.renders).toHaveLength(2);
    expect(db.renders[1].user_note).toBe("a warmer stone colour");
    expect(await screen.findByText("Your note: “a warmer stone colour”", {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("explains remaining check results in plain words", async () => {
    const { projectId, designId } = await seed("rendered", { railing: true });
    renderApp(`/projects/${projectId}/look?design=${designId}`);
    expect(await screen.findByText("Things to look at")).toBeInTheDocument();
    expect(screen.getByText("The railing may look slightly different from the material you chose.")).toBeInTheDocument();
  });

  it("“Change materials” goes back to step 4", async () => {
    const { projectId, designId } = await seed("rendered");
    renderApp(`/projects/${projectId}/look?design=${designId}`);
    expect(await screen.findByRole("link", { name: "Change materials" })).toHaveAttribute(
      "href",
      `/projects/${projectId}/materials?design=${designId}`,
    );
  });

  it("asks for a new look when the materials changed afterwards, and makes it from here", async () => {
    const { projectId, designId } = await seed("accepted");
    db.designs[0].assignments = db.designs[0].assignments.slice(1);
    const { user } = renderApp(`/projects/${projectId}/look?design=${designId}`);
    const stale = await screen.findByTestId("look-stale");
    expect(stale).toHaveTextContent("This look is out of date");
    expect(stale).toHaveTextContent(/Your materials changed after we created this look/);
    // The page explains it itself, so the banner does not repeat it here.
    expect(screen.queryByTestId("needs-update")).not.toBeInTheDocument();
    // An out-of-date look can't be accepted.
    expect(screen.queryByRole("button", { name: "I like it" })).not.toBeInTheDocument();
    await user.click(within(stale).getByRole("button", { name: "Create my new look again" }));
    expect(await screen.findByText("Creating your new look…")).toBeInTheDocument();
    expect(db.renders).toHaveLength(2);
    expect(db.renders[1].user_note).toBeNull();
  });

  it("has a helpful empty state", async () => {
    const { projectId, designId } = await seed("assigned");
    renderApp(`/projects/${projectId}/look?design=${designId}`);
    expect(await screen.findByText("You haven't created a new look for this design yet.")).toBeInTheDocument();
  });
});
