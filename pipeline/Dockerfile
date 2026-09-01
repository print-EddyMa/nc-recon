# TerraTriage assessment service.
#
#   docker build -t terratriage-api pipeline
#   docker run -p 8000:8000 \
#     -e HOST=0.0.0.0 \
#     -e CORS_ORIGINS=https://your-web-host.example \
#     -e TERRATRIAGE_TOKEN=change-me \
#     -v terratriage-data:/app/data \
#     terratriage-api
#
# The heuristic + torch (segmentation) damage backends run here. The Keras/TF
# xView2 CMU classifier needs a separate conda env and is local-only —
# `run.py infer --backend auto` falls back to heuristic when it is absent.
FROM python:3.11-slim

# GDAL / PROJ / GEOS for rasterio, shapely, pyproj, geopandas
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin libgdal-dev libgeos-dev libproj-dev proj-data \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        "torch" "torchvision"

COPY . .

# Warm the Maxar Open Data catalogue into data/cache at build time so the first
# /assess doesn't block on a cold GitHub crawl (and its 60 req/hr limit).
# Non-fatal: a build without network still produces a working image.
RUN python scripts/run.py events catalog || echo "[build] catalogue warm skipped"

# non-root
RUN useradd -m app \
    && mkdir -p /app/data/output /app/data/raw /app/data/cache \
               /app/served/tiles /app/served/data \
    && chown -R app /app
USER app

# ../web is not in the image — the service writes tiles + registry to a volume
# and serves them itself via GET /tiles/... and GET /events.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    TERRATRIAGE_TILES_DIR=/app/served/tiles \
    TERRATRIAGE_WEB_DATA_DIR=/app/served/data

VOLUME ["/app/data", "/app/served"]
EXPOSE 8000
CMD ["python", "server.py"]
