import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 30000,
  use: { baseURL: "http://127.0.0.1:4174", headless: true },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 850 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4174", url: "http://127.0.0.1:4174", reuseExistingServer: true },
});
