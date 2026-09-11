import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  // Only the frontend directory is served, never the Python project or models.
  server: { host: '127.0.0.1', port: 5173, strictPort: true, fs: { strict: true, allow: [root] } },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', clearMocks: true },
})
