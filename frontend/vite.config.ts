import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// frontend-vite-root: root pinned to this config file's directory so paths
// resolve consistently regardless of invocation cwd.
// frontend-build-output: outDir is absolute, pointing at the FastAPI static
// mount in src/sidestage/static.
// frontend-vite-proxy: dev server proxies /api (REST + SSE) to FastAPI on :8000.
//   NOTE: spec line 12/33 mentions a /ws proxy, but the current architecture
//   is REST + SSE — there is no WebSocket. Proxying /api covers both REST and
//   the SSE stream at /api/events.
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
        // SSE: keep the connection open and stream as-is.
        ws: false,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // Disable response buffering for text/event-stream so SSE frames
            // reach the browser without delay.
            const ct = proxyRes.headers['content-type'] ?? '';
            if (ct.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache';
            }
          });
        },
      },
    },
  },
});
