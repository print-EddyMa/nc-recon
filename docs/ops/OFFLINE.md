# Offline packs

*How to carry an assessed area to a laptop that will have no network: a
field command post, a shelter, a flight, a county building with the internet
down. Status: beta (see "How this was proven" below).*

## What works offline

On a laptop that already has Groma installed (repository, Python
environment, built web app) and has imported a pack, with the network off:

* open the app and the area;
* see the damage map over the area's own before and after imagery and a
  basemap (USGS The National Map topo);
* open any building: probabilities, evidence, before and after chips;
* record labels and work through Verify;
* export GeoPackage, File Geodatabase, KML, CSV with US National Grid and the
  FEMA damage-survey sheet;
* open the situation brief, and the response plan and its KML if the area's
  response products were built before packing.

What does **not** work offline, and says so on screen: new assessments
(imagery, structures and hazard data come from the network), live conditions
(river gauges, alerts, outages, shelters), FEMA assistance by ZIP code, Civil
Air Patrol photos that were not already cached, the 3-D terrain layer, and the
wildfire model (M1) on a laptop without its encoder file (it is only used by
new assessments, which are refused offline anyway). These routes answer
`503 this needs a network` at once instead of hanging.

## Make a pack (on a connected machine)

From `pipeline/`:

```
PYTHONPATH=src .venv/bin/python -m terratriage.ops.offline pack --area swannanoa --out /path/to/usb --tar
```

* About 30 to 60 MB for a 1.6 km area (Swannanoa: 455 files, 33.5 MB, 443
  basemap tiles); refused over 150 MB unless `--force`.
* `--with-web web/dist` also carries the built web app, for a laptop that has
  Groma's code but no built app.
* TEST (hold-out) areas are refused unless `--allow-test`.
* Building only reads the stored assessment and rasters; it writes nothing
  but the pack. Basemap tiles are downloaded at four requests a second and
  reused from `NCR_BASEMAP_DIR` when already there.

## Import it (on the laptop)

```
PYTHONPATH=src .venv/bin/python -m terratriage.ops.offline verify /path/to/groma-pack-swannanoa-20261022.tar
PYTHONPATH=src .venv/bin/python -m terratriage.ops.offline import /path/to/groma-pack-swannanoa-20261022.tar
```

Import checks every file against its sha256 first, refuses anything not in
the manifest, extracts a tar safely (regular files only, no absolute or parent
paths, no links), registers the event and area if this install does not know
them, and never touches labels. A different copy of the same area is
refused unless `--replace`.

Then start the server offline:

```
NCR_OFFLINE=1 TERRATRIAGE_TOKEN=<token> NCR_WEB_DIST=../web/dist .venv/bin/python server.py
```

`NCR_OFFLINE=1` makes the server refuse network-only routes, skip upstream
health probes, and send a Content Security Policy that lets the page reach
this server and nothing else.

## What a pack holds

| In the pack | Notes |
|---|---|
| `manifest.json` | format `groma-pack/1`, area, event and area specs, every file with sha256 and size, licences, what was left out |
| `outputs/<area>.*` | the assessment and its sidecars (impact, references, ground change, response products) |
| `raw/<area>/` | the before and after rasters as **display copies** (JPEG q85): for viewing and review only, never for re-assessment; the imagery sidecar |
| `cache/openfema/` | the event's FEMA declaration, so the event loads with no network |
| `basemap/{z}/{x}/{y}.jpg` | USGS The National Map topo tiles: zoom 6 to 12 over the area plus 25 km, 13 to 16 over the area plus 3 km (US Government, public domain) |

**Never in a pack:** street addresses (`<area>.responder.json`), labels,
Verify judgments, the audit log, the registry, the service token. A field
team that needs addresses takes the responder export from the EOC on an
encrypted device. See docs/ops/SECURITY.md.

## Labels made offline

Labels and Verify judgments made on the laptop stay on the laptop: version 1
has no sync back to the EOC. When the laptop is back, copy
`pipeline/data/labels/<area>.csv` (and `data/truth/<area>/`) to the EOC and
hand it to whoever runs the assessment.

## How this was proven

1. **Automated, with the network cut** (`pipeline/tests/test_offline.py`):
   a pack is built, imported into a fresh scratch install, and served by a
   new Python process whose sockets refuse and record any non-loopback
   connection. The test passes only with **zero** outbound attempts while
   the area list, the area, chips, imagery tiles, basemap tiles and style,
   the export (GeoPackage, KML, CSV), the brief, a label and a Verify task
   all work. Tampered, padded and unsafe packs are refused.
2. **Kernel-enforced, in a browser**: the Swannanoa pack imported into a
   scratch install and served under macOS `sandbox-exec` with all outbound
   network denied, the built web app driven in a browser through the map,
   3-D, Review, Respond, the export and Verify. 2026-10-22: 222 requests, all
   to the local server, no Content Security Policy errors; the pack was 455
   files, 33.5 MB; building it left the live outputs unchanged (41 files,
   identical sha256).
3. **Operator acceptance (to do before "beta" is dropped)**: on a real
   laptop, import a pack, turn Wi-Fi off, and run the checklist below.

## Wi-Fi-off checklist

1. Import the pack and start the server with `NCR_OFFLINE=1`.
2. Turn Wi-Fi off and unplug any network cable.
3. Open the app: the area is listed; the map shows the basemap and the
   after imagery; the screen says it is offline.
4. Open three buildings: chips load, probabilities show.
5. Record one label; open Verify and see a task.
6. Download the export; open the GeoPackage in QGIS or ArcGIS and the KML in
   Google Earth or TAK.
7. Open the situation brief.
8. Try New assessment: it says it needs a network.
9. Turn Wi-Fi back on; copy the labels file off the laptop.
