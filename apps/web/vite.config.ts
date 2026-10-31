/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      // Same origin in the browser, so the httpOnly session cookie works without CORS.
      // VITE_API_TARGET lets the end-to-end tests point the proxy at their own API instance.
      "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    css: false,
    testTimeout: 20000,
    environmentOptions: { jsdom: { url: "http://localhost:5173/" } },
  },
});
