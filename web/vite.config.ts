import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// `VITE_BASE` lets the app be hosted under a sub-path (e.g. GitHub Pages
// project sites). Defaults to '/'.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 2600, // deck.gl + maplibre are large and expected
  },
})
