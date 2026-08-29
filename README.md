# TerraTriage

Disaster damage assessment from satellite imagery. Given **pre- and post-event
imagery** of an area, TerraTriage locates every building and rates its damage on
the four-level xView2 scale — **no damage → minor → major → destroyed** — then
puts the result on an interactive 3-D map a response coordinator can actually
use.

Demo case: **Hurricane Helene**, western North Carolina, Sept–Oct 2024
(Old Fort & Spruce Pine).

|  |  |
|--|--|
| ![map](docs/shot-map.png) | ![landing](docs/shot-landing.png) |

## Layout

```
pipeline/   Phase A — Python. imagery + footprints + damage model -> GeoJSON
web/        Phase B — React/TS. the map app, reads that GeoJSON
docs/       PHASE_A_STATUS.md and notes
```

The two halves meet at one file: a GeoJSON `FeatureCollection` of building
polygons, each with a `damage_class` (0–3) and lon/lat. The schema is
`pipeline/src/terratriage/contract.py`, mirrored in `web/src/lib/types.ts`.

## Run it

### Pipeline (Phase A)

```bash
cd pipeline
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# real xView2 CMU baseline classifier (recommended): one-time TF env
conda create -y -n terratriage-tf python=3.11
conda run -n terratriage-tf pip install "tensorflow==2.15.1" "numpy<2" pillow

./.venv/bin/python scripts/run.py fetch --area old_fort   --lat 35.6293 --lon -82.1804
./.venv/bin/python scripts/run.py fetch --area spruce_pine --lat 35.9151 --lon -82.0643
./.venv/bin/python scripts/run.py infer --area old_fort        # -> data/output/old_fort.geojson
./.venv/bin/python scripts/run.py infer --area spruce_pine
./.venv/bin/python scripts/run.py validate --area old_fort     # -> data/output/old_fort_check.html
./.venv/bin/python scripts/make_tiles.py --area old_fort       # pre/post XYZ tiles for the app
```

Damage model: the pipeline auto-selects the **xView2 CMU baseline classifier**
(ResNet50-v1 + CNN head, trained on xBD) when its weights are present, else a
transparent change-detection heuristic. The xView2 **1st-place** Siamese-U-Net
ensemble is fully ported (`src/terratriage/models/`, `run.py infer-seg`) and
activates the moment `xview2_1st_weights.zip` is dropped in `pipeline/weights/`.
See `docs/PHASE_A_STATUS.md`.

### App (Phase B)

```bash
cd web
npm install
npm run sync-data          # copy pipeline output into public/data/
npm run dev
```

`npm run build` → static `dist/`. No backend — the app reads the GeoJSON and the
tiles as static files.

## Demo flow

Landing → drag the before/after wipe → **Open the damage map** → drag the bottom
slider from *3-D damage model* to *Satellite* and back → click a ranked
"hardest-hit cluster" to fly there → hover / click a building → switch to
**Spruce Pine** → **Summary** for the headline number.

## Credits & data

Imagery: [Maxar Open Data](https://www.maxar.com/open-data). Footprints:
OpenStreetMap (ODbL). Model & code: xView2 baseline (CMU SEI, BSD-3) and
1st-place solution (V. Durnov). Basemap: CARTO. Map: MapLibre GL + deck.gl.
