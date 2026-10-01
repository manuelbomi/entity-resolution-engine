import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Proxies /api calls to the FastAPI backend during local development, so
// the frontend code can just call fetch('/api/...') without worrying about
// which port the backend happens to be running on.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
