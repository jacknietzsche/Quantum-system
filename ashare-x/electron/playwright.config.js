import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  timeout: 30000,

  use: {
    baseURL: 'http://127.0.0.1:8766',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    // Use system Chrome to avoid downloading a separate browser
    channel: 'chrome',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'python main.py serve --port 8766',
    cwd: '../',
    url: 'http://127.0.0.1:8766/api/health',
    reuseExistingServer: true,
    timeout: 60000,
  },
})
