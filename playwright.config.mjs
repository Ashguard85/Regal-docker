import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  testMatch: '**/pwa_v10.spec.mjs',
  timeout: 30000,
  retries: 1,
  reporter: [['list']],
  webServer: {
    command: 'python -m http.server 8765 --bind 127.0.0.1 --directory frontend',
    url: 'http://127.0.0.1:8765/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 15000,
  },
});
