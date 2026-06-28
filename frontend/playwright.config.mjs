import { defineConfig } from '@playwright/test'

const PORT = process.env.PLAYWRIGHT_PORT || 4173
const baseURL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'edge',
      use: {
        browserName: 'chromium',
        channel: 'msedge',
        viewport: { width: 1280, height: 900 },
      },
    },
  ],
})
