import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    // React compiler uses a Rolldown-specific plugin; skip it during tests
    ...(mode !== 'test' ? [babel({ presets: [reactCompilerPreset()] })] : []),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8050',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/test/**/*.test.{ts,tsx}'],
  },
}))
