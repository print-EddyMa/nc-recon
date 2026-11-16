# The intro (`/intro.html`)

A self-running ~38 s opening for NC Recon: Helene on radar, the plunge into
Old Fort, the before / after, the read, the FEMA levels rising, what went to a
person, every assessed town, the title card with a way into the app.

It is a sibling of the 17.8 s pitch hook in `src/demo/` (which the recorded
video depends on and which is left untouched). Same build
(`vite.demo.config.ts`, the pinned map stack in `demo-deps/`), same baked
assets under `public/demo/`, plus three of its own under `public/intro/`.

```bash
npm run intro:assets     # bake public/intro/ from the pipeline's outputs (no network)
npm run demo:dev -- --port 5175     # then open http://localhost:5175/intro.html
npm run demo:build       # dist-demo/intro.html beside dist-demo/demo.html
```

`public/demo/basemap/` must exist (`npm run demo:assets`, network, once).

## What is real

Everything on screen is read from files, nothing is typed in:

| on screen | from |
| --- | --- |
| radar frames and their timestamps | `public/demo/radar/` (IEM NEXRAD archive) |
| before / after stills, the wide image | Maxar Open Data, the pair the assessment read |
| 2,206 structures, their FEMA levels and review flags | `public/intro/structures.json`, from `pipeline/data/output/ops/old_fort.geojson` |
| every count, range, run time, town | `public/intro/areas.json`, the same numbers `GET /ops/areas` serves |

`structures.json` carries outline, level and review flag only: no ids, no
addresses, no evidence. Old Fort is a TUNE area. The other towns appear only
as area-level counts, which are public anyway.

Two things are stylised and say so in the code: column height in the 3-D
shot is the damage level (a severity skyline, not building height), and the
"no damage" grey is a slate so it sits back on the dark stage. The
yellow-to-red ramp and the blue "needs a person" are the product's own.

## Controls and flags

Space / K play or pause · R restart · S, → or Esc skip to the title · F
fullscreen · D timecode.

| flag | effect |
| --- | --- |
| `?hold` | wait for Space instead of starting by itself |
| `?fixed` | fixed 60 fps step (a slow capture frame slows the playhead) |
| `?prewarm` | dense tile warm-up before the first frame |
| `?clean` | no buttons on the stage |
| `?debug` | timecode HUD |

Recording: `intro.html?hold&fixed&prewarm&clean`. For stills,
`window.__intro.seek(ms)` then screenshot.

With `prefers-reduced-motion` the page opens on the title card and offers the
sequence as a button.

## Where the camera can go

The offline basemap only holds tiles along the pitch demo's camera path. The
intro stays on them (see the note at the top of `beats.ts`): the descent and
the plunge are the demo's own path, everything at Old Fort is at zoom 14 or
closer, and the regional shot is a cut at zoom below 9. A new close-up
somewhere else needs those tiles baked first.

"Open NC Recon" goes to `VITE_APP_URL`, else the app's dev server in
development and `/` in a build.
