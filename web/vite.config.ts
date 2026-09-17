import { existsSync } from 'node:fs'
import { join } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const here = new URL('.', import.meta.url).pathname

// Phase H - the self-hosted demo basemap (public/demo/basemap/) is a partial
// tile pyramid: the camera path is covered, but a stray edge tile the enum
// missed must 404/204 cleanly, not fall through to the SPA index.html (which
// MapLibre would try to parse as a vector tile). Also stamp a content-type on
// .mvt so the vector-tile worker is happy.
//
// Every file under public/demo/basemap/ is content-baked (regenerated only by
// `npm run demo:assets`), so serve it `immutable` with a long max-age. Vite's
// static handler otherwise sends `Cache-Control: no-cache`, which makes MapLibre
// issue a conditional GET for every tile each time it re-enters the viewport -
// on the fast B3 snap / B6 pull-back those revalidation round-trips stack up
// behind the camera and the frame flies over un-painted ground. `immutable`
// turns each of those into a pure in-memory cache hit (the preload primes it).
function demoBasemapTiles(): Plugin {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mw = (req: any, res: any, next: any) => {
    const url: string = (req && req.url) || ''
    const path = url.split('?')[0]
    if (!path.startsWith('/demo/basemap/')) return next()
    const isTile = path.startsWith('/demo/basemap/tiles/') && path.endsWith('.mvt')
    if (isTile && !existsSync(join(here, 'public', path))) {
      // a bake-missed edge tile: hand back a zero-length 200 vector tile, NOT a
      // 204. MapLibre parses an empty body as an empty tile and marks it
      // `loaded`; a 204 can leave the tile un-terminal, so `areTilesLoaded()`
      // never settles for any view that includes it.
      res.statusCode = 200
      res.setHeader('Content-Type', 'application/x-protobuf')
      res.setHeader('Content-Length', '0')
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
      return res.end()
    }
    if (isTile) res.setHeader('Content-Type', 'application/x-protobuf')
    res.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
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
        // Phase H - the isolated scripted hook sequence (/demo.html)
        demo: `${here}demo.html`,
      },
    },
  },
})
