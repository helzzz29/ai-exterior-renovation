import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import "./index.css";
import { App } from "./App";
import { AppProviders } from "./AppProviders";
import { IS_MOCK } from "./lib/config";

async function boot() {
  if (IS_MOCK) {
    const { startMockApi } = await import("./mocks/browser");
    await startMockApi();
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppProviders>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AppProviders>
    </StrictMode>,
  );
}

void boot();
