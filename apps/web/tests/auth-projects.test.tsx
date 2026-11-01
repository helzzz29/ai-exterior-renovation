import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { expectPlainLanguage, location, login, renderApp, seed } from "./helpers";
import { server } from "./server";

describe("signing in", () => {
  it("sends signed-out visitors to the login page", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(location()).toBe("/login");
  });

  it("logs in and shows My projects", async () => {
    const { user } = renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "My projects" })).toBeInTheDocument();
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("explains a wrong password in plain words", async () => {
    const { user } = renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "wrongpassword");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That email and password don't match");
  });

  it("checks the form before sending it", async () => {
    const { user } = renderApp("/register");
    await user.type(await screen.findByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 8 characters");
  });

  it("creates an account", async () => {
    const { user } = renderApp("/register");
    await user.type(await screen.findByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "longenough");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(db.users.some((u) => u.email === "new@example.com")).toBe(true);
  });
});

describe("My projects", () => {
  it("shows a loading state, then the projects", async () => {
    await seed("regions");
    renderApp("/");
    expect(screen.getAllByText("Loading…").length).toBeGreaterThan(0);
    expect(await screen.findByText("Test house")).toBeInTheDocument();
    expect(screen.getByText("Check the parts of your house")).toBeInTheDocument();
    expectPlainLanguage();
  });

  it("shows a friendly error with a retry", async () => {
    login();
    server.use(http.get("/api/projects", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it.each(["Start my first project", "New project"])("“%s” opens the new-project screen", async (name) => {
    login();
    const { user } = renderApp("/");
    await screen.findByText("No projects yet");
    await user.click(screen.getByRole("link", { name }));
    await waitFor(() => expect(location()).toBe("/projects/new"));
    expect(await screen.findByRole("heading", { name: "Start a new project" })).toBeInTheDocument();
  });

  it("creates a project with an optional measurement", async () => {
    login();
    const { user } = renderApp("/projects/new");
    await user.click(await screen.findByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please give your project a name.");
    await user.type(screen.getByLabelText("Project name"), "Pune house");
    await user.type(screen.getByLabelText(/Width of the front/), "31");
    expect(screen.getByText(/A measurement gives the most accurate estimate/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(location()).toMatch(/\/projects\/.+\/photo$/));
    expect(db.projects[0].measurements.facade_width_ft).toBe(31);
    expect(await screen.findByRole("heading", { name: "Snap your home" })).toBeInTheDocument();
  });

  it("opens a project at the step it has reached", async () => {
    const { projectId } = await seed("regions");
    renderApp(`/projects/${projectId}`);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/parts`));
  });

  it("does not open steps that aren't ready yet", async () => {
    const { projectId } = await seed("upload");
    renderApp(`/projects/${projectId}/cost`);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/photo`));
  });
});
