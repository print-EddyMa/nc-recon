# Groma: one container = ops API + assessment worker + web app (same origin).
#
#   docker compose up -d --build            (see docker-compose.yml, docs/ops/DEPLOYMENT.md)
#
# Models, all built in so one `docker compose up -d --build` is a complete install:
#  * Groma's wildfire model (pipeline/data/model/weights, in git) + its ResNet-18
#    encoder (downloaded from download.pytorch.org, SHA-256 checked).
#  * The general image model (xView2 CMU baseline, BSD-3; trained on xBD,
#    non-commercial data terms): the `model` stage downloads the ONNX file from
#    Groma's `model-general-v1` release and checks its SHA-256. Build with
#    `--build-arg GROMA_GENERAL_MODEL=0` to skip it (CI does); Groma then says
#    that channel is off.

# ---------------------------------------------------- general image model --
# The xView2 baseline classifier, already converted to ONNX (BSD-3, licences/
# xview2-baseline-BSD-3.txt), from Groma's release; the SHA-256 is checked.
FROM python:3.13-slim AS model
ARG GROMA_GENERAL_MODEL=1
WORKDIR /m
RUN mkdir -p out && if [ "$GROMA_GENERAL_MODEL" = "1" ]; then \
      python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/print-EddyMa/nc-recon/releases/download/model-general-v1/xview2_cmu_classifier.onnx', 'out/xview2_cmu_classifier.onnx')" \
      && echo "711fbdd47d99c4e1d5e7d6a84ec5c8d1c8a5eaeb84ea90d1969e10cd02fdb18f  out/xview2_cmu_classifier.onnx" | sha256sum -c - ; \
    fi

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
# CPU builds of torch / torchvision first (the PyPI Linux wheels carry CUDA)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 torchvision==0.28.0 \
    && pip install -r requirements.txt

COPY pipeline/src ./src
COPY pipeline/scripts ./scripts
COPY pipeline/config ./config
COPY pipeline/server.py ./server.py
COPY LICENSE NOTICE licenses/ /app/licenses/
COPY pipeline/weights/ ./weights/
COPY --from=model /m/out/ ./weights/
COPY pipeline/data/model/weights/ ./model/weights/
ENV NCR_MODEL_DIR=/app/model TORCH_HOME=/app/torch
RUN PYTHONPATH=/app/src python -m terratriage.ops.model.fetch_encoder
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
