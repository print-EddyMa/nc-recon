# Deploying NC Recon

One container runs everything: the web app, the API and the assessment worker.
Caddy sits in front for HTTPS. No paid services or keys are required.

## Requirements

* A Linux or macOS host with Docker (4 CPU cores and 8 GB RAM minimum;
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
| `output/ops/` | assessments, impact, exports, briefs | By re-running (hours) |
| `raw/`, `cache/` | imagery pairs, source caches | Yes (re-fetched) |

Back up daily:

```bash
docker compose exec ncrecon python scripts/run.py ops-backup --out /app/data/backup.tar.gz
docker compose cp ncrecon:/app/data/backup.tar.gz ./ncrecon-backup-$(date +%F).tar.gz
```

## Operating

* Health: the Data sources panel, or `docker compose exec ncrecon python scripts/run.py ops-health`.
* Assessments run one at a time (CPU-bound); others queue (max 5). A small
  area takes about 2 minutes on 8 cores.
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
| `NCR_DEV_OPEN` | off | local development only |
