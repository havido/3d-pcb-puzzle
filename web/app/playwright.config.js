import { defineConfig } from '@playwright/test'

// Drives the real app in a real browser. Both servers must be up; if they already are
// (./web/dev.sh in another terminal), these are reused rather than started again.
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 7_000 },
  use: { baseURL: 'http://localhost:5173', trace: 'off', screenshot: 'only-on-failure' },
  webServer: [
    {
      command: 'cd ../.. && .venv/bin/uvicorn api.main:app --app-dir web --port 8765 --log-level warning',
      url: 'http://localhost:8765/api/health',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
