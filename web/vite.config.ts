import { existsSync } from 'node:fs'
import { join } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const here = new URL('.', import.meta.url).pathname

// Phase H — the self-hosted demo basemap (public/demo/basemap/) is a partial
// tile pyramid: the camera path is covered, but a stray edge tile the enum
// missed must 404/204 cleanly, not fall through to the SPA index.html (which
// MapLibre would try to parse as a vector tile). Also stamp a content-type on
// .mvt so the vector-tile worker is happy.
function demoBasemapTiles(): Plugin {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mw = (req: any, res: any, next: any) => {
    const url: string = (req && req.url) || ''
    const path = url.split('?')[0]
    if (!path.startsWith('/demo/basemap/tiles/') || !path.endsWith('.mvt')) return next()
    if (!existsSync(join(here, 'public', path))) {
      res.statusCode = 204 // MapLibre treats an empty response as an empty tile
      return res.end()
    }
    res.setHeader('Content-Type', 'application/x-protobuf')
    next()
  }
  return {
    name: 'demo-basemap-tiles',
    configureServer(server) {
      server.middlewares.use(mw)
    },
    configurePreviewServer(server) {
      server.middlewares.use(mw)
    },
  }
}

// https://vite.dev/config/
// `VITE_BASE` lets the app be hosted under a sub-path (e.g. GitHub Pages
// project sites). Defaults to '/'.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), demoBasemapTiles()],
  build: {
    chunkSizeWarningLimit: 2600, // deck.gl + maplibre are large and expected
    rollupOptions: {
      input: {
        // the interactive app
        main: `${here}index.html`,
        // Phase H — the isolated scripted hook sequence (/demo.html)
        demo: `${here}demo.html`,
      },
    },
  },
})
