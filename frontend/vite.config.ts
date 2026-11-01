import { defineConfig } from "vitest/config";
export default defineConfig({
  base: "/app/",
  build: { outDir: "../app/webapp", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom" },
});
