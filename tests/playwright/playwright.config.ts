import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

// Run via `just test-browser` from the repo root. That recipe picks an
// ephemeral port (via `get-port-cli`), exports it as
// `SIDESTAGE_TEST_PORT`, then invokes playwright. The port is owned by
// the shell, so it propagates cleanly to playwright's main process and
// every worker subprocess via standard env inheritance.

const REPO_ROOT = path.resolve(__dirname, '../..');

const portStr = process.env.SIDESTAGE_TEST_PORT;
const port = portStr ? parseInt(portStr, 10) : NaN;
if (!Number.isInteger(port) || port <= 0) {
  throw new Error(
    'SIDESTAGE_TEST_PORT is unset or invalid. Invoke via ' +
      '`just test-browser`, which picks an ephemeral port before ' +
      'running playwright. Direct `npm run test` is unsupported.',
  );
}
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? 'list' : [['list'], ['html', { open: 'never' }]],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], baseURL },
    },
  ],
  webServer: {
    command: `uv run sidestage --sidestage-dir tests/sidestage/ --port ${port}`,
    cwd: REPO_ROOT,
    url: `${baseURL}/api/campaigns`,
    // Never reuse; we own the ephemeral port and want the right campaign.
    reuseExistingServer: false,
    timeout: 10_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
