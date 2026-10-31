import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { db } from "@/mocks/db";
import { formatINR } from "@/lib/format";
import { expectPlainLanguage, renderApp, seed } from "./helpers";

describe("Step 6: Cost & report", () => {
  it("shows each line, the range in rupees and a measured badge", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    expect((await screen.findAllByText("Exterior emulsion paint")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Natural stone cladding").length).toBeGreaterThan(0);
    expect(screen.getByTestId("estimate-kind")).toHaveTextContent("Measured estimate");
    expect(screen.getByTestId("total-range").textContent).toMatch(/^About ₹[\d,]+ \(likely between ₹[\d,]+ and ₹[\d,]+\)$/);
    expect(screen.getByText("Includes exterior primer")).toBeInTheDocument();
    expectPlainLanguage();

    const [how] = screen.getAllByRole("button", { name: "How was this calculated?" });
    await user.click(how);
    const steps = screen.getByTestId("derivation");
    expect(within(steps).getByText(/Plus 5% for cutting and wastage/)).toBeInTheDocument();
    expect(within(steps).getByText(/^Labour:/)).toBeInTheDocument();
  });

  it("shows a rough estimate until the size check is done", async () => {
    const { projectId, designId } = await seed("assigned");
    db.projects[0].scale_confirmed = false;
    renderApp(`/projects/${projectId}/cost?design=${designId}`);
    expect(await screen.findByTestId("estimate-kind")).toHaveTextContent("Rough estimate");
    expect(screen.getByRole("button", { name: "Finalise estimate" })).toBeDisabled();
    expect(screen.getByText("Finish the size check before finalising.")).toBeInTheDocument();
  });

  it("editing a price highlights it and updates the totals after saving", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const before = (await screen.findByTestId("grand-total")).textContent;
    const field = screen.getByLabelText("Material price (₹ per sq ft)");
    expect(field).toHaveAttribute("data-changed", "false");
    await user.clear(field);
    await user.type(field, "200");
    expect(field).toHaveAttribute("data-changed", "true");
    expect(screen.getByRole("button", { name: "Use the usual price" })).toBeInTheDocument();
    await waitFor(() => expect(db.projects[0].overrides).toEqual([{ material_id: "stone-natural", material_rate: 200, labour_rate: null }]));
    await waitFor(() => expect(screen.getByTestId("grand-total").textContent).not.toBe(before));
    expect(screen.getByText("Changed")).toBeInTheDocument();
  });

  it("extras can be changed", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const tax = await screen.findByLabelText("Tax, GST (%)");
    await user.clear(tax);
    await user.type(tax, "0");
    await waitFor(() => expect(db.projects[0].extras.tax_pct).toBe(0));
    await waitFor(() => expect(screen.getAllByText(formatINR(0)).length).toBeGreaterThan(0));
  });

  it("download stays locked until the look is accepted and the estimate finalised", async () => {
    const { projectId, designId } = await seed("rendered");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const download = await screen.findByRole("button", { name: "Download report" });
    expect(download).toBeDisabled();
    expect(screen.getByTestId("report-checklist")).toHaveTextContent("Accept your new look");
    await user.click(screen.getByRole("button", { name: "Finalise estimate" }));
    expect(await screen.findByTestId("finalised")).toHaveTextContent("Estimate finalised (version 1)");
    expect(screen.getByRole("button", { name: "Download report" })).toBeDisabled();
    expect(screen.queryByTestId("next-steps")).not.toBeInTheDocument();
  });

  it("finalise + accepted look: one click builds the report and downloads the PDF", async () => {
    // jsdom has no object URLs
    const created = vi.fn(() => "blob:report");
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() });
    const names: string[] = [];
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download);
    });
    const { projectId, designId } = await seed("accepted");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    await user.click(await screen.findByRole("button", { name: "Finalise estimate" }));
    const download = await screen.findByRole("button", { name: "Download report" });
    await waitFor(() => expect(download).toBeEnabled());
    await user.click(download);
    expect(await screen.findByText("Preparing your report…")).toBeInTheDocument();
    await waitFor(() => expect(clicked).toHaveBeenCalledTimes(1), { timeout: 8000 });
    expect(created).toHaveBeenCalled();
    expect(names[0]).toMatch(/renovation report v1\.pdf$/);
    expect(screen.queryByRole("button", { name: /Open the report/ })).not.toBeInTheDocument();
    // the journey ends with clear next steps
    const next = await screen.findByTestId("next-steps");
    expect(within(next).getByText("All done: your report is downloaded")).toBeInTheDocument();
    expect(within(next).getByRole("link", { name: "Back to my projects" })).toHaveAttribute("href", "/");
    // Opens the same design again (it does not make a new one), so it says so.
    expect(within(next).getByRole("link", { name: "Change this design" })).toHaveAttribute(
      "href",
      `/projects/${projectId}/materials?design=${designId}`,
    );
    expect(within(next).getByRole("link", { name: "Start a new project" })).toHaveAttribute("href", "/projects/new");
    // a second click downloads the same, already built report straight away
    await waitFor(() => expect(screen.getByRole("button", { name: "Download report" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Download report" }));
    await waitFor(() => expect(clicked).toHaveBeenCalledTimes(2));
    vi.restoreAllMocks();
  });

  it("a price change after finalising asks to finalise again", async () => {
    const { projectId, designId } = await seed("accepted");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    await user.click(await screen.findByRole("button", { name: "Finalise estimate" }));
    await screen.findByTestId("finalised");
    const field = screen.getByLabelText("Labour price (₹ per sq ft)", { selector: "#lab-paint-emulsion" });
    await user.clear(field);
    await user.type(field, "20");
    expect(
      await screen.findByText(
        "Your estimate changed after you finalised it. Review it and finalise it again to update the report.",
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("report-checklist")).toHaveTextContent("Finalise your estimate again");
    expect(screen.getByRole("button", { name: "Download report" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Finalise estimate" })).toBeInTheDocument();
  });
});
