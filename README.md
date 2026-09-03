# NC Recon

A **North Carolina disaster application** with two halves:

- **Risk monitor** — the "before / during": NOAA NWPS river-flood **forecasts**,
  USGS streamflow, NWS watches & warnings, NHC active-storm tracking, NASA FIRMS
  active fire, NCDOT DriveNC cameras & closures, OpenFEMA disaster history, and
  (with a free key) ECONet / RAWS current conditions from the NC State Climate
  Office CLOUDS API. This is what the app opens on.
- **Damage assessment** — the "after": point it at an area of North Carolina,
  and it pulls the pre/post Maxar Open Data imagery for that footprint, locates
  every building, rates its damage on the four-level xView2 scale
  (**no damage → minor → major → destroyed**), fuses two independent models plus
  NC context priors into a per-building **confidence tier**, and puts the result
  on an interactive 3-D map with a **human review queue** for the uncertain calls.

Nothing is pre-baked. There is no bundled sample dataset — areas appear on the
damage map only after the pipeline has assessed them (locally, or against a
hosted assessment service).

## Layout

```
pipeline/   Python. imagery + footprints + fusion model + NC priors -> GeoJSON
              footprints.py   OSM / NC OneMap building polygons for an AOI
              fusion.py       dual-model + calibration.json -> confidence tier
              context.py      NC flood-stage / FEMA / terrain priors
              server.py       the assessment service (POST /assess, NC-gated)
              scripts/calibrate.py   tune the tier thresholds for an area
web/        React/TS. NC risk dashboard + on-demand Assess + damage map + review
              lib/nc.ts       NC backbone (NWPS/USGS/NWS/NHC/FIRMS/DriveNC/FEMA/CLOUDS)
              screens/NCDashboard.tsx   the risk dashboard (the front door)
              screens/Assess.tsx        drop an NC AOI -> run the pipeline
docs/       PHASE_A_STATUS.md, PHASE_CD_STATUS.md, PHASE_E_STATUS.md
```

The two halves meet at one file: a GeoJSON `FeatureCollection` of building
polygons, each with a `damage_class` (0–3), lon/lat, and — schema **1.1** — a
`confidence_tier` (`high` / `review`), a `sources` dict (`{heuristic, cnn,
margin}`, plus `priors`/`prior_effect` when `--nc-context` is used) and
`footprint_source`. The schema is `pipeline/src/terratriage/contract.py`,
mirrored in `web/src/lib/types.ts`. `web/public/data/events.json` (written by
`run.py events registry`) is the registry of assessed NC areas — it ships as
`[]`.

## Run it locally

### Web app

```bash
cd web
npm install
npm run refresh-nc         # seed public/data/nc/*_snapshot.geojson (offline fallback)
npm run dev                # http://localhost:5173
```

The app is a static site. With no `VITE_API_URL` it runs fully — the NC risk
dashboard is all live public feeds — and the **Assess** screen shows the CLI
commands to run an assessment yourself. Copy `web/.env.example` to
`web/.env.development.local` (dev only; never read by `vite build`) to set
`VITE_API_URL` (a running assessment service), `VITE_FIRMS_KEY` (active-fire
layer), or `VITE_BASE` (sub-path hosting).

`refresh-nc` refreshes the committed snapshots the dashboard falls back to when
a feed is unavailable: NWPS / USGS / NWS are also fetched live in-app
(open, CORS-enabled); NHC and DriveNC are CORS-blocked in the browser so the
snapshot is the only path. CLOUDS needs a free per-user hash — paste it in-app
(Layers → key).

### Assessment pipeline

```bash
cd pipeline
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install torch torchvision      # optional: segmentation backend

# optional: the real xView2 CMU baseline classifier (local only, needs conda)
conda create -y -n terratriage-tf python=3.11
conda run -n terratriage-tf pip install "tensorflow==2.15.1" "numpy<2" pillow

# assess one NC area (Old Fort, McDowell County)
./.venv/bin/python scripts/run.py fetch --event HurricaneHelene-Oct24 \
    --area old_fort --lat 35.6293 --lon -82.1804 --event-date 2024-09-26 \
    --name "Old Fort" --subtitle "McDowell County, NC"
./.venv/bin/python scripts/run.py infer --area old_fort --source auto --nc-context
./.venv/bin/python scripts/make_tiles.py --area old_fort
./.venv/bin/python scripts/run.py events registry     # -> web/public/data/events.json
./.venv/bin/python scripts/run.py events catalog      # -> web/public/data/maxar_catalog.json

# tune the confidence-tier thresholds for that area (optional)
./.venv/bin/python scripts/calibrate.py --area old_fort --labels labels.csv --write
```

`--source auto` uses NC OneMap building footprints when
`TERRATRIAGE_NC_FOOTPRINTS_URL` points at an NC building-footprint ArcGIS
FeatureServer, otherwise OpenStreetMap. `--nc-context` folds nearest-gauge flood
stage, active FEMA declarations, and terrain slope into the confidence tiers
(network calls; they only move borderline tiers, never the damage class).
`--backend auto` picks **fusion** when the CNN weights + `terratriage-tf` env are
present, else `keras`, else `heuristic`.

### Assessment service

```bash
cd pipeline
./.venv/bin/python server.py                  # http://127.0.0.1:8000
```

Then set `VITE_API_URL=http://127.0.0.1:8000` for the web app and the Assess
screen gains a one-click **Assess this area** button. The service only accepts
AOIs inside North Carolina.

## Deploy

**Web**: `npm run build` → static `dist/`. Host anywhere (Netlify / Vercel /
Pages / S3). Set `VITE_API_URL` at build time to wire in a hosted assessment
service; without it the site is the live NC risk monitor plus the manual Assess
instructions.

**Assessment service** (optional):

```bash
docker build -t terratriage-api pipeline
docker run -p 8000:8000 \
  -e HOST=0.0.0.0 \
  -e CORS_ORIGINS=https://your-web-host.example \
  -e TERRATRIAGE_TOKEN=change-me \
  -v terratriage-data:/app/data -v terratriage-served:/app/served \
  terratriage-api
```

Config (all optional, env): `TERRATRIAGE_TOKEN` (bearer auth on `/assess` +
`DELETE`), `CORS_ORIGINS`, `ALLOWED_BBOX` (`w,s,e,n`, default NC),
`MAX_ACTIVE_JOBS`, `MAX_ASSESS_PER_HOUR`, `MAX_DATA_GB`, `HOST`, `PORT`,
`TERRATRIAGE_NC_FOOTPRINTS_URL`, `TERRATRIAGE_TILES_DIR`,
`TERRATRIAGE_WEB_DATA_DIR`. The hosted image runs the heuristic + torch
segmentation backends; the Keras/TF CMU classifier is local-only.

## Using it

The app **opens on the NC risk monitor** (`#/`, or **g** then **n**). Toggle
layers on the left; the right panel ranks the flood forecast, lists active NWS
alerts, shows current conditions and fire weather, an **NC disaster history**
panel (OpenFEMA), and the nearest DriveNC cameras + closures to the worst
current risk point.

**Assess** (`#/assess`, or **g** then **a**): click anywhere in North Carolina
to drop an AOI, pick the Maxar event that covers it, and run the pipeline —
one click with a service connected, or copyable commands without one. When it
finishes, the **Damage map**, **Review** queue and **Summary** light up for
that area (deep-linked `#/a/<area>/<screen>`).

Keyboard: **⌘K** command menu, **?** shortcut list, **g** then
`n`/`a`/`m`/`r`/`s`.

## Credits & data

Imagery: [Maxar Open Data](https://www.maxar.com/open-data) via the
[opengeos/maxar-open-data](https://github.com/opengeos/maxar-open-data) STAC
mirror. Footprints: OpenStreetMap (ODbL), NC OneMap. Model & code: xView2
baseline (CMU SEI, BSD-3) and 1st-place solution (V. Durnov). NC risk & context:
[NOAA NWPS](https://water.noaa.gov/), [USGS NWIS](https://waterservices.usgs.gov/),
[NWS](https://www.weather.gov/documentation/services-web-api),
[NHC](https://www.nhc.noaa.gov/), [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/),
[NCDOT DriveNC](https://drivenc.gov/), [OpenFEMA](https://www.fema.gov/about/openfema/api),
[USGS EPQS](https://apps.nationalmap.gov/epqs/), and the NC State Climate Office
[CLOUDS API](https://api.climate.ncsu.edu/). Multi-source-fusion + human-review
pattern after HOT's [fAIr](https://www.hotosm.org/). Basemap: CARTO. Map:
MapLibre GL + deck.gl.
