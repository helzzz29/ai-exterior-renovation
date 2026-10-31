/**
 * Screen behaviour checks. Uses the mock API,
 * like the other screen tests; nothing here talks to the real server.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { AICallOut } from "@/api/types";
import { db } from "@/mocks/db";
import { groupTrace } from "@/features/trace/TracePanel";
import { stepStatuses } from "@/features/wizard/progress";
import { call, location, login, renderApp, seed } from "./helpers";
import { server } from "./server";

describe("sign in and the app frame", () => {
  it("starts each form clean when switching between log in and create account", async () => {
    const { user } = renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "longenough");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription("Please enter a valid email address.");
    expect(email).toHaveFocus();
    await user.click(screen.getByRole("link", { name: "New here? Create an account" }));
    expect(await screen.findByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("");
  });

  it("can show the password while typing it", async () => {
    const { user } = renderApp("/register");
    const pw = await screen.findByLabelText("Password");
    expect(pw).toHaveAttribute("type", "password");
    expect(pw).toHaveAccessibleDescription("At least 8 characters.");
    await user.click(screen.getByRole("button", { name: "Show" }));
    expect(pw).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide" }));
    expect(pw).toHaveAttribute("type", "password");
  });

  it("names the header links and marks the current section", async () => {
    login();
    renderApp("/");
    await screen.findByText("No projects yet");
    expect(screen.getByRole("link", { name: "Home Makeover Planner: my projects" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "My projects" })).toHaveAttribute("aria-current", "page");
  });

  it("sends the user to log in when the session runs out mid-use, then back to the same screen", async () => {
    const { projectId } = await seed("regions");
    server.use(
      http.get("/api/projects/:id", () =>
        HttpResponse.json({ code: "unauthorised", message: "Please log in to continue." }, { status: 401 }),
      ),
    );
    const { user } = renderApp(`/projects/${projectId}/photo`);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(location()).toBe("/login");
    server.resetHandlers();
    await user.type(screen.getByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/photo`));
    expect(await screen.findByRole("heading", { name: "Your photo" })).toBeInTheDocument();
  });
});

describe("projects", () => {
  it("asks in the page before deleting, and Cancel keeps the project", async () => {
    await seed("upload");
    const { user } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Delete Test house" }));
    const dialog = screen.getByRole("dialog", { name: "Delete “Test house”?" });
    expect(dialog).toHaveTextContent("It can't be undone.");
    expect(within(dialog).getByRole("button", { name: "Keep project" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Keep project" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(db.projects).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Delete Test house" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete project" }));
    expect(await screen.findByText("Project deleted")).toBeInTheDocument();
    expect(db.projects).toHaveLength(0);
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("a missing project offers the way back instead of a retry that can't work", async () => {
    login();
    renderApp("/projects/does-not-exist/photo");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't find that. It may have been deleted.");
    expect(within(alert).getByRole("link", { name: "Back to my projects" })).toHaveAttribute("href", "/");
    expect(within(alert).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("shows every field problem at once, next to its field, and clears it when fixed", async () => {
    login();
    const { user } = renderApp("/projects/new");
    await user.type(await screen.findByLabelText(/Width of the front/), "0");
    await user.type(screen.getByLabelText("Number of floors"), "12");
    await user.click(screen.getByRole("button", { name: "Create project" }));
    expect(screen.getByLabelText("Project name")).toHaveAccessibleDescription(/Please give your project a name./);
    expect(screen.getByLabelText(/Width of the front/)).toHaveAccessibleDescription("Please enter a number above zero.");
    expect(screen.getByLabelText("Number of floors")).toHaveAccessibleDescription("Please enter between 1 and 10 floors.");
    expect(screen.getByLabelText("Project name")).toHaveFocus();
    await user.type(screen.getByLabelText("Project name"), "A");
    expect(screen.getByLabelText("Project name")).not.toHaveAttribute("aria-invalid");
    expect(db.projects).toHaveLength(0);
    expect(screen.getByRole("link", { name: "Back to my projects" })).toHaveAttribute("href", "/");
  });
});

describe("wizard frame", () => {
  it("only ticks steps whose work is really done", async () => {
    const { projectId, designId } = await seed("assigned");
    renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const nav = await screen.findByRole("navigation", { name: "Your progress" });
    expect(await within(nav).findByRole("link", { name: /Choose materials.*Done/ })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Your new look.*Not started/ })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /Your new look.*Done/ })).not.toBeInTheDocument();
  });

  it("keeps the chosen design when a project is reopened by its address", async () => {
    const { projectId, designId } = await seed("designing");
    renderApp(`/projects/${projectId}?design=${designId}`);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/materials?design=${designId}`));
  });

  it("doesn't repeat the size question in a banner on the size check itself", async () => {
    const { projectId } = await seed("scale");
    renderApp(`/projects/${projectId}/size`);
    expect(await screen.findByText("Does this look right?")).toBeInTheDocument();
    expect(screen.queryByTestId("needs-update")).not.toBeInTheDocument();
  });

  it("phones get a compact step menu that lists every step", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    const toggle = await screen.findByRole("button", { name: /Step 2 of 6.*Parts of your house/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    const menu = document.getElementById("step-menu")!;
    expect(within(menu).getAllByRole("listitem")).toHaveLength(6);
    expect(within(menu).getByRole("link", { name: /Your photo/ })).toBeInTheDocument();
  });
});

describe("step statuses", () => {
  const project = { stage: "designing" as const, photo: { id: "ph", url: "x", width: 1, height: 1 }, regions_approved: true, scale_confirmed: true };
  const design = { assignments: [], render: null, estimate_finalised: false, estimate_stale: false };
  it("reads the real state of each step", () => {
    expect(stepStatuses(project, design)).toEqual(["done", "done", "done", "todo", "todo", "todo"]);
    const stale = { ...design, assignments: [{ region_id: "r", material_id: "m", color: null }], render: { id: "x", status: "accepted" as const, stale: true, attempts: 1, created_at: "" }, estimate_finalised: true, estimate_stale: true };
    expect(stepStatuses(project, stale).slice(3)).toEqual(["done", "stale", "stale"]);
    expect(stepStatuses({ ...project, stage: "regions_review", regions_approved: false }, null)).toEqual([
      "done",
      "attention",
      "locked",
      "locked",
      "locked",
      "locked",
    ]);
    expect(stepStatuses({ ...project, stage: "photo_warning", photo: null }, null)[0]).toBe("attention");
  });
});

describe("photo", () => {
  function pick(name: string, type = "image/jpeg") {
    fireEvent.change(screen.getByTestId("photo-input"), { target: { files: [new File(["x"], name, { type })] } });
  }

  it("“Replace photo” can be cancelled without changing anything", async () => {
    const { projectId } = await seed("regions");
    const jobs = db.jobs.length;
    const { user } = renderApp(`/projects/${projectId}/photo`);
    await user.click(await screen.findByRole("button", { name: "Replace photo" }));
    expect(screen.getByText("Drag your photo here")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep my current photo" }));
    expect(screen.getByText(/Photo checked/)).toBeInTheDocument();
    expect(db.jobs.length).toBe(jobs);
    expect(db.projects[0].stage).toBe("regions_review");
  });

  it.each([
    ["a lost connection", () => HttpResponse.error(), "We couldn't upload your photo"],
    [
      "the daily limit",
      () => HttpResponse.json({ code: "daily_limit", message: "You've reached today's limit of photo checks." }, { status: 429 }),
      "Daily limit reached",
    ],
  ])("titles an upload problem by its cause: %s", async (_name, reply, title) => {
    const { projectId } = await seed("upload");
    server.use(http.post("/api/projects/:id/photo", reply));
    renderApp(`/projects/${projectId}/photo`);
    await screen.findByText("Drag your photo here");
    pick("house.jpg");
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByText("This photo won't work")).not.toBeInTheDocument();
  });

  it("a wrong file type gets its own title", async () => {
    const { projectId } = await seed("upload");
    renderApp(`/projects/${projectId}/photo`);
    await screen.findByText("Drag your photo here");
    pick("plan.pdf", "application/pdf");
    expect(await screen.findByText("That file type won't work")).toBeInTheDocument();
  });
});

describe("parts editor", () => {
  it("says why Continue is blocked while a part is being drawn", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Add a part" }));
    await user.click(screen.getByRole("button", { name: "Start with a box instead" }));
    expect(screen.getByText("Finish or cancel the part you're adding first.")).toBeInTheDocument();
    expect(screen.queryByText("Answer every “Please check” question first.")).not.toBeInTheDocument();
  });

  it("adds a part and moves its corners without a mouse", async () => {
    const { projectId } = await seed("regions");
    const before = db.projects[0].regions.length;
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Add a part" }));
    expect(screen.getByText("0 corners so far")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start with a box instead" }));
    await user.click(within(screen.getByTestId("type-picker")).getByRole("button", { name: "Gate" }));
    expect(within(screen.getByTestId("selected-card")).getByText("Gate")).toBeInTheDocument();
    await waitFor(() => expect(db.projects[0].regions.length).toBe(before + 1));
    // still selected after the save gave it its saved id
    await waitFor(() => expect(screen.getByTestId("selected-card")).toBeInTheDocument());
    const card = screen.getByTestId("selected-card");
    const added = db.projects[0].regions[db.projects[0].regions.length - 1];
    const x0 = added.polygon[0][0];
    await user.click(within(card).getByText("Adjust the corners"));
    await user.click(within(card).getByRole("button", { name: "Move right" }));
    await waitFor(() => {
      const now = db.projects[0].regions.find((r) => r.label === "gate" && r.polygon[0][0] !== x0);
      expect(now).toBeDefined();
    });
  });

  it("shows a close-up that always contains the whole part", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Pillar Please check" }));
    const crop = within(screen.getByTestId("check-card")).getByTestId("crop-preview");
    expect(crop.getAttribute("preserveAspectRatio")).toBe("xMidYMid meet");
    expect(crop.getAttribute("viewBox")).toMatch(/^\d+ \d+ \d+ \d+$/);
  });

  it("saves the last answer when leaving the screen straight away", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Pillar Please check" }));
    await user.click(within(screen.getByTestId("check-card")).getByRole("button", { name: "Yes" }));
    await user.click(screen.getByRole("link", { name: /Your photo/ }));
    await waitFor(() => expect(db.projects[0].regions.find((r) => r.id === "p-pillar-r")?.checked).toBe(true));
  });
});

describe("materials", () => {
  it("design tabs move with the arrow keys and label their panel", async () => {
    const { projectId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    await user.click(await screen.findByRole("button", { name: "Duplicate" }));
    const copyTab = await screen.findByRole("tab", { name: "Design 1 (copy)" });
    await waitFor(() => expect(copyTab).toHaveAttribute("aria-selected", "true"));
    const first = screen.getByRole("tab", { name: "Design 1" });
    expect(first).toHaveAttribute("tabindex", "-1");
    copyTab.focus();
    await user.keyboard("{ArrowLeft}");
    expect(first).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", copyTab.id);
  });

  it("the material list is one radio group: arrow keys move and choose", async () => {
    const { projectId, designId } = await seed("designing");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    const wall = await screen.findByRole("radiogroup", { name: /Main wall/ });
    const keep = within(wall).getByRole("radio", { name: "Keep as it is" });
    expect(keep).toHaveAttribute("tabindex", "0");
    keep.focus();
    await user.keyboard("{ArrowDown}");
    const chosen = within(wall).getAllByRole("radio")[1];
    expect(chosen).toHaveAttribute("aria-checked", "true");
    expect(chosen).toHaveFocus();
    await waitFor(() => expect(db.designs.find((d) => d.id === designId)?.assignments).toHaveLength(1));
    // closed groups sum up the choice
    await user.click(screen.getByRole("button", { name: /^Pillar/ }));
    expect(screen.getByRole("button", { name: /^Main wall/ })).not.toHaveTextContent("Kept as it is");
  });
});

describe("your new look", () => {
  it("offers Before / Compare / After buttons and counts the note", async () => {
    const { projectId, designId } = await seed("rendered");
    const { user } = renderApp(`/projects/${projectId}/look?design=${designId}`);
    const group = await screen.findByRole("group", { name: "Choose what the picture shows" });
    expect(within(group).getByRole("button", { name: "Compare" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(group).getByRole("button", { name: "After" }));
    expect(within(group).getByRole("button", { name: "After" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Change something" }));
    const note = screen.getByLabelText("Tell us what to change, e.g. a warmer stone colour");
    await user.type(note, "warmer");
    expect(note).toHaveAccessibleDescription("6 of 500 characters");
    await user.click(screen.getByRole("button", { name: "Cancel and clear" }));
    await user.click(screen.getByRole("button", { name: "Change something" }));
    expect(screen.getByLabelText("Tell us what to change, e.g. a warmer stone colour")).toHaveValue("");
  });

  it("shows which design it is about, with its look and estimate state", async () => {
    const { projectId, designId } = await seed("accepted");
    renderApp(`/projects/${projectId}/look?design=${designId}`);
    const bar = await screen.findByTestId("design-bar");
    expect(bar).toHaveTextContent("Design 1");
    expect(bar).toHaveTextContent("Accepted");
    expect(bar).toHaveTextContent("Not finalised");
  });
});

describe("cost & report", () => {
  it("explains a wrong price next to the field and does not save it", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const field = await screen.findByLabelText("Material price (₹ per sq ft)");
    await user.clear(field);
    await user.type(field, "-5");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Please enter a price of zero or more.");
    expect(screen.getByText("Fix the highlighted field to update the totals.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finalise estimate" })).toBeDisabled();
    await new Promise((r) => setTimeout(r, 300));
    expect(db.projects[0].overrides).toEqual([]);
  });

  it("keeps a price typed just before leaving the screen", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const field = await screen.findByLabelText("Material price (₹ per sq ft)");
    await user.clear(field);
    await user.type(field, "321");
    await user.click(screen.getByRole("link", { name: /Choose materials/ }));
    await waitFor(() =>
      expect(db.projects[0].overrides).toEqual([{ material_id: "stone-natural", material_rate: 321, labour_rate: null }]),
    );
  });

  it("names what still blocks the report, right next to the locked button", async () => {
    const { projectId, designId } = await seed("assigned");
    renderApp(`/projects/${projectId}/cost?design=${designId}`);
    const list = await screen.findByTestId("report-checklist");
    expect(within(list).getByRole("link", { name: "Create your new look and accept it" })).toHaveAttribute(
      "href",
      `/projects/${projectId}/look?design=${designId}`,
    );
    expect(list).toHaveTextContent("Finalise your estimate");
    const download = screen.getByRole("button", { name: "Download report" });
    expect(download).toBeDisabled();
    expect(download).toHaveAccessibleDescription(/The report unlocks when both of these are done/);
  });
});

describe("how we worked this out", () => {
  let n = 0;
  const c = (step: string, stage: AICallOut["stage"]): AICallOut => ({
    id: `t${++n}`,
    step,
    stage,
    title: step,
    summary: "",
    ok: true,
    attention: false,
    new_run: false,
    provider: "jev",
    model: "m",
    latency_ms: 1000,
    cost_usd: null,
    confidence: null,
    attempts: 1,
    cached: false,
    created_at: "2026-10-25T13:00:00Z",
  });

  it("labels a second photo check as a second run", () => {
    const groups = groupTrace([c("C1", "photo"), c("C2", "photo"), c("C3", "photo"), c("C1", "photo"), c("C2", "photo")]);
    expect(groups.map((g) => [g.stage, g.run, g.steps.length])).toEqual([
      ["photo", 1, 3],
      ["photo", 2, 2],
    ]);
  });

  it("loads again every time it is opened", async () => {
    const { projectId } = await seed("regions");
    let loads = 0;
    server.use(
      http.get("/api/projects/:id/ai-calls", () => {
        loads++;
        return undefined;
      }),
    );
    const { user } = renderApp(`/projects/${projectId}/parts`);
    const toggle = await screen.findByRole("button", { name: "How we worked this out" });
    await user.click(toggle);
    await screen.findByText("Found the parts of your house");
    await user.click(toggle);
    await user.click(toggle);
    await waitFor(() => expect(loads).toBe(2));
    expect(await call("GET", `/api/projects/${projectId}/ai-calls`)).toBeTruthy();
  });
});
