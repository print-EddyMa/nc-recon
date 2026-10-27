# Groma: one container = ops API + assessment worker + web app (same origin).
#
#   docker compose up -d --build            (see docker-compose.yml, docs/ops/DEPLOYMENT.md)
#
# Models, all built in so one `docker compose up -d --build` is a complete install:
#  * Groma's wildfire model (pipeline/data/model/weights, in git) + its ResNet-18
#    encoder (downloaded from download.pytorch.org, SHA-256 checked).
#  * The general image model (xView2 CMU baseline, non-commercial terms): the
#    `model` stage downloads its weights from the public xView2 baseline release,
#    checks the SHA-256 and converts them to ONNX. Build with
#    `--build-arg GROMA_GENERAL_MODEL=0` to skip it (CI does); Groma then says
#    that channel is off. A local pipeline/weights/xview2_cmu_classifier.onnx is
#    used as is when present.

# ---------------------------------------------------- general image model --
# TF 2.15 is the only runtime that loads the 2019 Keras weights faithfully; it
# lives only in this throwaway stage, never in the runtime image. The conversion
# peaks near 5 GB, so the other stages wait for it (out/.done) instead of
# running beside it on an 8 GB Docker host.
FROM python:3.11-slim AS model
ARG GROMA_GENERAL_MODEL=1
WORKDIR /m
COPY pipeline/src/terratriage/_keras_infer.py pipeline/scripts/export_onnx.py ./
RUN mkdir -p out && if [ "$GROMA_GENERAL_MODEL" = "1" ]; then \
      pip install --no-cache-dir tensorflow==2.15.1 tf2onnx==1.16.1 onnx==1.16.2 \
      && python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/DIUx-xView/xView2_baseline/releases/download/v1.0/classification.hdf5', 'classification.hdf5')" \
      && echo "a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd  classification.hdf5" | sha256sum -c - \
      && mkdir -p src/terratriage && mv _keras_infer.py src/terratriage/ && mkdir scripts && mv export_onnx.py scripts/ \
      && python scripts/export_onnx.py classification.hdf5 out/xview2_cmu_classifier.onnx \
      && rm classification.hdf5; \
    fi \
    && touch out/.done

# ---------------------------------------------------------------- web build --
FROM node:22-slim AS web
WORKDIR /web
COPY --from=model /m/out/.done /tmp/model.done
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
COPY --from=model /m/out/.done /tmp/model.done
COPY pipeline/requirements.txt ./requirements.txt
# CPU builds of torch / torchvision first (the PyPI Linux wheels carry CUDA)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 torchvision==0.28.0 \
    && pip install -r requirements.txt

COPY pipeline/src ./src
COPY pipeline/scripts ./scripts
COPY pipeline/config ./config
COPY pipeline/server.py ./server.py
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
