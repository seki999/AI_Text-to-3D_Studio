import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 2,
  use: {
    baseURL: "http://127.0.0.1:5174",
    actionTimeout: 15000,
    navigationTimeout: 30000,
    headless: true,
    viewport: { width: 1920, height: 1080 },
  },
  webServer: {
    command: "npm run dev -- --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
  timeout: 180000,
});
