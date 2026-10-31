import "@testing-library/jest-dom/vitest";
import "vitest-canvas-mock";
import { cleanup, configure } from "@testing-library/react";

// Test files run in parallel; give screens a little longer to settle on slow machines.
configure({ asyncUtilTimeout: 6000 });
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

// Konva's Node build needs the native `canvas` package. The canvases only draw pictures (the
// same information is in the HTML around them), so tests use light stand-ins.
vi.mock("react-konva", async () => {
  const React = await import("react");
  const make = (name: string) =>
    function KonvaStub({ children }: { children?: React.ReactNode }) {
      return React.createElement("div", { "data-konva": name }, children);
    };
  return {
    Stage: make("Stage"),
    Layer: make("Layer"),
    Group: make("Group"),
    Line: make("Line"),
    Rect: make("Rect"),
    Circle: make("Circle"),
    Text: make("Text"),
    Image: make("Image"),
  };
});
import { resetDb } from "@/mocks/db";
import { server } from "./server";

// jsdom gaps used by Radix menus and tooltips.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
if (!window.matchMedia) {
  window.matchMedia = (q: string) =>
    ({
      matches: false,
      media: q,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
// No screen uses the native confirm() any more; make any accidental use fail loudly.
window.confirm = () => {
  throw new Error("window.confirm should not be used; use ConfirmDialog");
};
// jsdom has <dialog> but not its modal methods (used by ConfirmDialog).
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
if (!("ResizeObserver" in window)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  resetDb();
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
