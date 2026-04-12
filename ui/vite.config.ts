import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'

export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] }),
  ],
  server: {
    // Proxy API calls to the Flask dev server during development
    proxy: {
      '/api': 'http://localhost:8050',
    },
  },
})
