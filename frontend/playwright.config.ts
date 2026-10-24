import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: process.env.E2E_URL || "http://127.0.0.1:18080",
    viewport: { width: 1365, height: 900 },
    launchOptions: process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {},
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
