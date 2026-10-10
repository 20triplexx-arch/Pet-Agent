import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8011",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command:
      (process.platform === "win32"
        ? "..\\.venv\\Scripts\\python.exe"
        : "../.venv/bin/python") + " -m scripts.e2e_server",
    cwd: "../backend",
    url: "http://127.0.0.1:8011/health",
    reuseExistingServer: false,
    timeout: 45000,
  },
});
