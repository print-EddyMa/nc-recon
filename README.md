# NC Recon

Disaster damage decision support for North Carolina emergency management.

After a declared (or provisional) event, point NC Recon at a town in North
Carolina. It pulls before- and after-event imagery (NC OneMap orthos, NOAA
emergency aerials or Maxar Open Data), finds every structure (FEMA USA
Structures, OpenStreetMap, USACE National Structure Inventory), and estimates
each structure's **FEMA damage level with a probability**. Uncertain and
severe calls go to a **human review queue**, and every call carries its reasons
and the evidence it could not check. It estimates **people likely displaced**
and ranks census tracts by need. Outputs are GeoJSON, CSV with US National
Grid, KML, GeoPackage, File Geodatabase, a Survey123 field sheet, homes in the
field layout of FEMA's IA damage survey, and a
one-page situation brief. A **Conditions** map shows live river gauges and
flood forecasts (USGS, NOAA and NC Emergency Management's FIMAN network), NWS
alerts, power outages by county, open shelters, road closures, DOT cameras and
active storms.

> Decision-support tool. Not an official FEMA or NC Emergency Management
> damage assessment. Verify on the ground. **Accuracy is not yet validated**:
> no public structure-level ground truth exists for Helene in NC, so the
> system measures itself only from analyst labels
> (`docs/ops/LABELING_PROTOCOL.md`, `reports/ACCURACY_REPORT.md`).

No paid services or keys are used. Optional free keys add layers (see Help).

## Deploy (one container + HTTPS)

```bash
cp /path/to/xview2_cmu_classifier.onnx pipeline/weights/   # damage model, not in git
cp .env.example .env        # set TERRATRIAGE_TOKEN (long random) and NCR_DOMAIN
docker compose up -d --build
```

Open `https://<NCR_DOMAIN>/`, paste the token under Operations → Responder
access. Full guide, security model, backups: [`docs/ops/DEPLOYMENT.md`](docs/ops/DEPLOYMENT.md).

## Use

* **Operations** (home): a map of every assessed area; **New assessment**
  (pick a point, see the square it will cover, check imagery, run); jobs in
  progress with their step, run time and a cancel button; inside an area, the
  structures over the before / after imagery the assessment read, structure
  cards, a review queue with keyboard labeling, the situation brief, GIS
  export, public tract summary, FEMA assistance by ZIP code, **Run again**;
  data-source status and accuracy.
* **Conditions**: statewide live hazards.
* **Help**: how to read every number, what the system cannot see.

Event playbook: [`docs/ops/OPERATIONS.md`](docs/ops/OPERATIONS.md).
Verified ground truth (blind multi-verifier labeling, consensus, dataset):
[`docs/truth/README.md`](docs/truth/README.md).
Working with NC emergency offices: [`docs/outreach/PLAN.md`](docs/outreach/PLAN.md)
(plan, first email, printable one-pager).

## Develop locally

```bash
# API + worker (Python 3.13)
cd pipeline
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
NCR_DEV_OPEN=1 .venv/bin/python server.py          # :8000, auth off (dev only)
.venv/bin/python -m pytest tests -q                 # offline suite; -m live hits upstreams

# web (Node 22)
cd web
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.development.local
npm run dev                                         # :5173
```

Pipeline CLI (`pipeline/scripts/run.py`): `ops-health`, `ops-fetch`,
`ops-assess`, `ops-impact`, `ops-export`, `ops-brief`, `ops-aggregate`,
`ops-reference`, `ops-eval`, `ops-calibrate`, `ops-backup`. More in
[`pipeline/README.md`](pipeline/README.md).

## Layout

```
pipeline/
  server.py                 FastAPI: /ops API, live feeds, serves the built web app
  src/terratriage/ops/      operational pipeline (GEOINT cycle)
    plan/                   events (OpenFEMA), windows, TUNE/TEST/OPS areas
    collect/                connectors with health checks
    process/                geodesy-aware imagery, co-registration, alignment, structures
    analyze/                evidence channels, fusion, calibration, evaluation, impact
    disseminate/            exports, brief, public aggregates, map tiles
    api.py jobs.py auth.py  HTTP API, assessment queue, access control
  config/                   events, context rules, crosswalks, FEMA damage matrix
  tests/                    pytest
web/
  src/screens/              Ops, NCDashboard (Conditions), Help
  src/demo/, demo-deps/     offline pitch demo (separate build: npm run demo:build)
docs/ops/                   deployment, operations, data sources, labeling, status
MODEL_CARD.md BIAS_AUDIT.md LICENSES.md
```

## Pitch demo

The scripted demo from the Congressional App Challenge is kept as an offline
recording tool with its own pinned map stack: `npm run demo:dev`,
`npm run demo:build`, `npm run demo:validate`. It is not part of the deployed
app. The pre-operational build is tagged `cac-v2-demo-stable`.

Beside it, `web/intro.html` is a longer self-running intro in the product's
own vocabulary (FEMA levels, the current Old Fort assessment, every assessed
town): [`web/src/intro/README.md`](web/src/intro/README.md).

## Credits and licenses

Data: USGS, NOAA (NWPS, NWS, NHC, NGS ERI), NCDOT DriveNC, OpenFEMA, FEMA USA
Structures, USACE NSI, NC OneMap / NC Collaboratory, Maxar Open Data
(CC BY-NC 4.0), OpenStreetMap contributors (ODbL), CDC/ATSDR SVI, CARTO
basemaps. Model: xView2 baseline classifier (non-commercial terms). See
[`LICENSES.md`](LICENSES.md).
