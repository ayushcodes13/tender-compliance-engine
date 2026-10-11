import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT ?? "3207";
const backendPort = String(Number(port) + 1);
const baseURL = `http://127.0.0.1:${port}`;
const backendURL = `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: [["line"]],
  use: { baseURL, ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `node e2e/proxy-backend.mjs ${backendPort}`,
      url: `${backendURL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `node e2e/start-standalone.mjs ${port} ${backendURL}`,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
