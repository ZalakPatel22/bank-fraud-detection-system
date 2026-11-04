import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // GitHub Pages serves this project from /bank-fraud-detection-system/.
  // Use the ordinary root path while developing locally.
  base: process.env.GITHUB_ACTIONS ? '/bank-fraud-detection-system/' : '/',
  plugins: [react()],
  server: {
    // Keep local API requests same-origin in the browser and avoid CORS issues.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
