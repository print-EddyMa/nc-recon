// Build / dev config for the offline pitch demo (demo.html) and intro (intro.html).
//   npm run demo:dev | demo:build | demo:preview
// The demo's map stack resolves to demo-deps/node_modules (maplibre-gl 5 +
// deck.gl 9.3, pinned from the cac-v2-demo-stable tag). The product build
// (vite.config.ts) never includes the demo.
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { demoBasemapTiles } from './vite.config'

const here = new URL('.', import.meta.url).pathname
const dep = (p: string) => `${here}demo-deps/node_modules/${p}`

export default defineConfig({
  plugins: [react(), demoBasemapTiles()],
  resolve: {
    alias: [
      { find: /^maplibre-gl\/dist\/(.*)$/, replacement: dep('maplibre-gl/dist/$1') },
      { find: /^maplibre-gl$/, replacement: dep('maplibre-gl') },
      { find: /^@deck\.gl\/(core|layers|mapbox)$/, replacement: dep('@deck.gl/$1') },
    ],
  },
  build: {
    outDir: 'dist-demo',
    chunkSizeWarningLimit: 2600,
    // demo.html: the 17.8 s hook for the pitch video. intro.html: the longer
    // self-running intro built on the same baked assets (src/intro/).
    rollupOptions: { input: { demo: `${here}demo.html`, intro: `${here}intro.html` } },
  },
  preview: { port: 4173 },
})
