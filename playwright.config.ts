import { defineConfig } from "@playwright/test";
export default defineConfig({
  globalSetup: "./tests/global-setup.ts",
  testDir: "./tests",
  workers: 1,
  use: {
    storageState: ".local/playwright-auth.json",
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
  reporter: "list",
});
