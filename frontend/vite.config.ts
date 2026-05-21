import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// frontend-vite-root: root pinned to this config file's directory so paths
// resolve consistently regardless of invocation cwd.
// frontend-build-output: outDir is absolute, pointing at the FastAPI static
// mount in src/sidestage/static.
// frontend-vite-proxy: dev server proxies /api (REST + WebSocket) to FastAPI
//   on :8000. The multiplexed WS at /api/campaigns/{cid}/ws goes through this
//   same proxy with ws: true.
export default defineConfig({
  plugins: [react()],
  root: path.resolve(__dirname),
  build: {
    outDir: path.resolve(__dirname, '../src/sidestage/static'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // WebSocket proxy: forwards Upgrade requests to FastAPI's WS route.
        ws: true,
      },
    },
  },
  // frontend-test: vitest config. jsdom for DOM; setup file wires
  // @testing-library/jest-dom matchers. Colocated *.test.tsx pattern.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
