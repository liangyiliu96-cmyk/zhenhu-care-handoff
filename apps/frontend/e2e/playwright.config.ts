import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './flows',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: 1,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    headless: true,
  },
  webServer: [
    {
      command: 'set PYTHONPATH=src;../../packages/clinical-contracts-py/src&& python -m uvicorn zhenhu.inpatient.main:app --host 127.0.0.1 --port 8001',
      cwd: '../../services/inpatient-ward',
      url: 'http://127.0.0.1:8001/health',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
