import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/sidestage': {
        target: 'http://localhost:8000',
        ws: true
      },
      '/agents': 'http://localhost:8000',
      '/sessions': 'http://localhost:8000',
    }
  }
})
