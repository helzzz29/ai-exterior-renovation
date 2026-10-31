import { setupWorker } from "msw/browser";
import { enablePersistence } from "./db";
import { handlers } from "./handlers";

export async function startMockApi(): Promise<void> {
  enablePersistence();
  const worker = setupWorker(...handlers);
  await worker.start({
    onUnhandledRequest: "bypass",
    quiet: true,
  });
}
