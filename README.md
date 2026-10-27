# Groma

**Every building, after the disaster.** Groma calls the damage to every
building from public imagery, lidar and field records, so search teams,
emergency managers, insurers and aid groups start in the right place.

Free during launch. Open source under the [Apache License 2.0](LICENSE).
Pilots and questions: **ma.eddy.work@gmail.com**.

> Decision support. Not an official FEMA or state emergency management damage
> assessment. Verify on the ground.

## What it does

* **Assess.** Type a FEMA disaster number. Groma reads the declaration, finds
  before and after imagery for any US state, finds every building, and gives
  each one of FEMA's five damage levels with a probability and the evidence
  behind it. Flood, wind, wildfire, earthquake and landslide.
* **Verify.** Uncertain and severe calls go to people, who judge them blind,
  with Civil Air Patrol photos of the building.
* **Respond.** Roads likely cut, people cut off, lifelines at risk,
  landing-zone candidates and 1 km search sectors in US National Grid, as KML
  for TAK and Google Earth.
* **Export.** FEMA's damage survey fields, GeoPackage, File Geodatabase, KML,
  CSV, a situation brief, and the state's initial damage assessment packet in
  the formats FEMA's July 2025 PDA guide accepts.
* **Share.** A private, expiring record of one building for a verified owner
  (for a FEMA appeal or an insurer), a public "is my street OK?" check that
  never shows one home, and the Groma Index of public counts per area.
* **Offline (beta).** Carry an assessed area to a field laptop with no network.

## Who it's for

| | What they get |
|---|---|
| Emergency management (counties, states, tribes) | Damage counts the day imagery arrives; the IDA packet; ranked search sectors |
| Insurers and lenders | A call per building with its evidence, from a method you can inspect and re-run |
| National Guard and responders | An offline field kit, TAK-ready KML, USNG sectors, landing-zone candidates |
| Aid groups and nonprofits | Area-level counts for targeting cash and supplies, never one home |
| Researchers and AI labs | Calls checked by people, field records to compare against, fresh test sets |
| Residents | Through a county or legal aid partner: their street, and a private record of their home |

## Results so far

* **Eaton fire, 2025 (wildfire model, held out):** of 2,246 buildings CAL FIRE
  inspected, when Groma called a building Major or Destroyed the inspectors
  agreed 95.7% of the time, and Groma found 94.2% of the ones they marked that
  way. One run, rule fixed before it ran; the wildfire model alone, not the
  whole system. Details: [`docs/model/MODEL_CARD.md`](docs/model/MODEL_CARD.md).
* **Swannanoa, Hurricane Helene:** 893 buildings in 88 seconds on one laptop.
  Flood is harder: water inside a house does not show from above, so Groma
  found 15 of the 64 homes county search teams recorded as Major or
  Destroyed. Flood accuracy is still being validated, and every severe call
  goes to people before it counts.

## Get started

### Run it (one container, HTTPS, both models built in)

```bash
cp .env.example .env    # set TERRATRIAGE_TOKEN, NCR_OWNER_SECRET and NCR_DOMAIN
docker compose up -d --build
```

The build downloads and checks both damage models: Groma's wildfire model and
its encoder, and the general image model from this repo's
[`model-general-v1`](https://github.com/print-EddyMa/nc-recon/releases/tag/model-general-v1) release.
Open `https://<NCR_DOMAIN>/` and paste the token under **Sign in**. Full guide,
security model and backups: [`docs/ops/DEPLOYMENT.md`](docs/ops/DEPLOYMENT.md).

### Develop locally

```bash
# API and worker (Python 3.13)
cd pipeline
python3 -m venv .venv
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 torchvision==0.28.0   # Linux; on macOS plain pip is fine
.venv/bin/pip install -r requirements-dev.txt
PYTHONPATH=src .venv/bin/python -m terratriage.ops.model.fetch_encoder   # wildfire model encoder
NCR_DEV_OPEN=1 .venv/bin/python server.py           # :8000, auth off (dev only)
.venv/bin/python -m pytest tests -q                  # offline suite

# web (Node 22)
cd web
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.development.local
npm run dev                                          # :5173
```

The general image model (flood and wind) is a 474 MB download; locally, see
[`pipeline/weights/README.md`](pipeline/weights/README.md). Without it Groma
runs and says that channel is off.

## Documentation

* Launch checklist (ready, and what still needs a person): [`docs/LAUNCH.md`](docs/LAUNCH.md)
* Event playbook: [`docs/ops/OPERATIONS.md`](docs/ops/OPERATIONS.md)
* Deployment and configuration: [`docs/ops/DEPLOYMENT.md`](docs/ops/DEPLOYMENT.md)
* Any hazard, any state: [`docs/ops/ANY_HAZARD.md`](docs/ops/ANY_HAZARD.md)
* Offline field packs: [`docs/ops/OFFLINE.md`](docs/ops/OFFLINE.md)
* Response products: [`docs/response/README.md`](docs/response/README.md)
* Verified ground truth: [`docs/truth/README.md`](docs/truth/README.md)
* Models: [`docs/model/MODEL_CARD.md`](docs/model/MODEL_CARD.md), [`MODEL_CARD.md`](MODEL_CARD.md), [`BIAS_AUDIT.md`](BIAS_AUDIT.md)
* Data sources and licences: [`docs/ops/DATA_SOURCES.md`](docs/ops/DATA_SOURCES.md), [`LICENSES.md`](LICENSES.md)
* Design system: [`DESIGN.md`](DESIGN.md)
* Website: [`site/`](site/) (`python3 site/build.py`)

## Layout

```
pipeline/
  server.py                 FastAPI: /ops API, live feeds, serves the built web app
  src/terratriage/ops/      plan, collect, process, analyze, disseminate, response, model, offline
  config/                   events, hazards, context rules, crosswalks, FEMA damage matrix
  tests/                    pytest (offline)
web/                        React app: Assess, Verify, Conditions, Help; public check, index, owner record
site/                       the public website
docs/                       operations, deployment, models, data
```

## Pricing

Free during launch: every feature, self-hosted or as a pilot we run with you.
Paid hosting and support will come later and will be announced well before
anything changes. To request a pilot: **ma.eddy.work@gmail.com**.

## Licence, data and security

Code: Apache-2.0 ([`LICENSE`](LICENSE), [`NOTICE`](NOTICE)). Groma reads
public data whose own terms travel with the outputs (OpenStreetMap is ODbL;
Maxar Open Data and the xView2 baseline model are non-commercial): see
[`LICENSES.md`](LICENSES.md). Report a vulnerability privately: [`SECURITY.md`](SECURITY.md).
