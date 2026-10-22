# Deploying NC Recon

One container runs everything: the web app, the API and the assessment worker.
Caddy sits in front for HTTPS. No paid services or keys are required.

## Requirements

* A Linux (x86_64 or arm64) or macOS host with Docker; the image builds for
  both architectures (x86_64 verified with `docker buildx --platform linux/amd64`) (4 CPU cores and 8 GB RAM minimum;
  more cores make assessments faster). About 3 GB for the image, plus data.
* Outbound HTTPS to the public data sources (USGS, NOAA, FEMA, NC OneMap,
  NOAA ERI on AWS, Maxar Open Data on AWS, OpenStreetMap Overpass, USACE NSI).
* The damage model file `xview2_cmu_classifier.onnx` (not in git; see
  "Model" below).

## First deployment

```bash
git clone <repo> nc-recon && cd nc-recon
# 1. model: copy it into pipeline/weights/ (or mount it, see below)
cp /path/to/xview2_cmu_classifier.onnx pipeline/weights/
# 2. settings
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into TERRATRIAGE_TOKEN
#    set NCR_DOMAIN to the host name analysts will use
# 3. build + start
docker compose up -d --build
docker compose logs -f ncrecon     # wait for "Uvicorn running"
```

Open `https://<NCR_DOMAIN>/`. Analysts paste the token once under
**Operations → Responder access**. Share the token only with responders.

## Security model

* **Token required.** Structure-level results, image chips, addresses,
  labels, exports, briefs, new assessments and event registration all need
  `Authorization: Bearer <TERRATRIAGE_TOKEN>`. The server refuses to start
  on a non-loopback address without a token. There is no "trusted
  localhost": behind the proxy every request is local, so none is trusted.
* **Public without a token:** area summaries, tract-level public summaries
  (no addresses, counts under 5 withheld), people/need by tract, data-source
  health, the accuracy report, and the Conditions map.
* `NCR_DEV_OPEN=1` disables auth for local development only; the server
  refuses to combine it with a non-loopback bind.
* HTTPS is terminated by Caddy (automatic certificates for a real domain).
  Do not expose port 8000 directly.
* Rotate the token by editing `.env` and `docker compose up -d`.
* **Rate limits** per client address: 30 writes, 600 reads and 120 feed
  requests a minute (`NCR_RATE_*_PER_MIN`); over the limit answers 429 with
  `Retry-After`. Behind the bundled Caddy the client address is read from
  `X-Forwarded-For` because compose sets `NCR_TRUST_PROXY=1`; without that
  flag the header is ignored, since anyone can forge it.
* **Browser security headers** on every response: a Content Security Policy
  that allows scripts only from this origin (plus a hash of the theme
  bootstrap in `index.html`), direct connections only to the basemap, radar
  and federal feed hosts the app uses (`NCR_CSP_CONNECT` adds more, e.g. a
  self-hosted basemap), no framing, no referrer, `nosniff`, no caching of
  API responses, HSTS from Caddy. Fonts are bundled, so the only hosts the
  browser needs besides this one are the basemap, radar and feed hosts.
* **Dependencies**: CI fails on a high-severity advisory in a runtime
  dependency (`pip-audit`, `npm audit --omit=dev`) and publishes a CycloneDX
  SBOM for the image's Python and JavaScript dependencies.

## Model

The CNN is the xView2 baseline classifier exported to ONNX
(`pipeline/scripts/export_onnx.py`, run once in the TensorFlow conda env).
SHA-256 `711fbdd47d99c4e1d5e7d6a84ec5c8d1c8a5eaeb84ea90d1969e10cd02fdb18f`.
Either bake it in (copy to `pipeline/weights/` before `docker compose build`)
or mount it:

```yaml
    volumes:
      - /secure/models/xview2_cmu_classifier.onnx:/models/cnn.onnx:ro
    environment:
      NCR_MODEL_PATH: /models/cnn.onnx
```

The Data sources panel shows `damage model DOWN` if it is missing.

## Data and backups

Everything the system writes lives in the `ncrecon-data` volume (`/app/data`):

| Path | What | Re-derivable? |
|---|---|---|
| `labels/*.csv` | **Ground-truth labels from analysts** | **No: the most valuable data in the system** |
| `ops_registry.yaml` | provisional events + operational areas | No |
| `jobs.json` | recent assessment jobs (status, steps, errors) | No (history only) |
| `output/ops/` | assessments, impact, exports, briefs | By re-running (hours) |
| `audit.log` | who did what: assess, view, label, export, brief, delete (UTC, client address) | No |
| `raw/`, `cache/` | imagery pairs, source caches, map tiles cut from the imagery | Yes (re-fetched) |

Back up daily:

```bash
docker compose exec ncrecon python scripts/run.py ops-backup --out /app/data/backup.tar.gz
docker compose cp ncrecon:/app/data/backup.tar.gz ./ncrecon-backup-$(date +%F).tar.gz
```

## When sources are down

Federal services fail during disasters. NC Recon degrades rather than stops:

| Source down | Effect |
|---|---|
| OpenFEMA | cached declaration, else the one shipped in the image (Helene); new events can be registered manually |
| USACE NSI | assessment completes; no occupancy/foundation data, flood depth unavailable, occupants from USA Structures; warning shown |
| CDC SVI / Census | people estimate still computed; need index marked unavailable |
| OpenStreetMap | USA Structures footprints only; warning shown |
| USA Structures **and** OpenStreetMap, or the imagery service | that assessment fails cleanly (no partial output); others unaffected |

Verified by blackholing hosts in the container (`--add-host=<host>:127.0.0.1`).

## Operating

* Health: the Data sources panel, or `docker compose exec ncrecon python scripts/run.py ops-health`.
* Assessments run one at a time (CPU-bound); others queue (max 5). A small
  area takes about 2 minutes on 8 cores. Operations lists every job with its
  step and run time, and **Cancel** stops one (its partial output is removed).
* A restart ends the running assessment. On start-up the server marks any job
  that was queued or running as interrupted and removes the area it had half
  registered; analysts see it under In progress and run it again.
* Run one server per data directory. Two servers on the same `data/` would
  each treat the other's running assessment as left over from a crash.
* The data-source board is refreshed in the background (at most every 10
  minutes, or on **Check again**), so a slow upstream never holds up a page.
* Evaluation after labeling: `ops-eval`, then `ops-calibrate` (TUNE labels only),
  then re-run assessments so outputs use calibrated probabilities.
* Playbook for an event: `docs/ops/OPERATIONS.md`.

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `TERRATRIAGE_TOKEN` | (none; required when exposed) | responder bearer token |
| `NCR_DOMAIN` | localhost | Caddy host name |
| `NCR_CENSUS_API_KEY` | (none) | free; enables seasonal-home adjustment |
| `NCR_USGS_API_KEY` | (none) | free; higher USGS rate limits |
| `NCR_MODEL_PATH` | `/app/weights/xview2_cmu_classifier.onnx` | damage model |
| `NCR_CPU_THREADS` | cores − 2 | model threads |
| `NCR_STEP_TIMEOUT_S` | 1800 | per-step job timeout |
| `NCR_CONTACT` | project URL | email or URL sent in the User-Agent to federal APIs (weather.gov asks for one) |
| `NCR_TRUST_PROXY` | off (compose sets 1) | read the client address from `X-Forwarded-For` |
| `NCR_RATE_WRITE_PER_MIN` / `NCR_RATE_READ_PER_MIN` / `NCR_RATE_FEED_PER_MIN` | 30 / 600 / 120 | per-client rate limits |
| `NCR_CSP_CONNECT` | (none) | extra origins the browser may call directly |
| `NCR_DEV_OPEN` | off | local development only |
