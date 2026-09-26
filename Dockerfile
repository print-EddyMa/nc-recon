# NC Recon: one container = ops API + assessment worker + web app (same origin).
#
#   docker compose up -d --build            (see docker-compose.yml, docs/ops/DEPLOYMENT.md)
#
# The damage model is NOT committed. Put xview2_cmu_classifier.onnx in
# pipeline/weights/ before building (it is copied in if present), or mount it
# and set NCR_MODEL_PATH. Without it every structure goes to human review and
# the health board shows damage_model DOWN.

# ---------------------------------------------------------------- web build --
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY web/ ./
# same-origin build: the app talks to the API that serves it; no keys baked in
ENV VITE_SAME_ORIGIN=1
RUN npx vite build

# ------------------------------------------------------------------ runtime --
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# rasterio / pyogrio / pyproj / shapely wheels bundle GDAL, PROJ and GEOS;
# the GDAL wheels still expect the system expat (XML) library
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
COPY pipeline/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY pipeline/src ./src
COPY pipeline/scripts ./scripts
COPY pipeline/config ./config
COPY pipeline/server.py ./server.py
COPY pipeline/weights/ ./weights/
COPY --from=web /web/dist /app/web

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/raw /app/data/output /app/data/cache /app/data/labels \
                /app/data/runs /app/data/calibration /app/data/reports /app/served \
    && chown -R app /app/data /app/served
USER app

ENV HOST=0.0.0.0 \
    PORT=8000 \
    NCR_WEB_DIST=/app/web \
    TERRATRIAGE_WEB_DATA_DIR=/app/served \
    TERRATRIAGE_TILES_DIR=/app/served/tiles \
    NCR_RUNS_DIR=/app/data/runs \
    NCR_CALIBRATION_DIR=/app/data/calibration \
    NCR_REPORTS_DIR=/app/data/reports \
    CORS_ORIGINS=

VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"
CMD ["python", "server.py"]
