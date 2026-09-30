/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, /api is proxied to the FastAPI service (uvicorn covenantwatch.api:app --port 8901).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8901', rewrite: (p) => p.replace(/^\/api/, '') } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
