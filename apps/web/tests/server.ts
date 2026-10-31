import { setupServer } from "msw/node";
import { handlers } from "@/mocks/handlers";

/** The mock API from src/mocks, served to the tests. Use `server.use(...)` to override a route. */
export const server = setupServer(...handlers);
