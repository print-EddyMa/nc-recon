#!/bin/sh
# Run NC Recon from this computer, public at the Netlify address (deploy/home/README.md).
#
#   deploy/home/live.sh setup    once: data folder, secrets
#   deploy/home/live.sh start    server + tunnel + front end (deploys if NETLIFY_AUTH_TOKEN is set)
#   deploy/home/live.sh stop
#   deploy/home/live.sh status
set -eu

REPO=$(cd "$(dirname "$0")/../.." && pwd)
LIVE=${NCR_LIVE_DIR:-$HOME/ncrecon-live}
PORT=${NCR_LIVE_PORT:-8100}
PY="$REPO/pipeline/.venv/bin/python"
SITE_ID=${NCR_NETLIFY_SITE:-4febd40e-f76b-4d34-b227-ba149bacd919}
RUN="$LIVE/run"

load_env() {
  [ -f "$LIVE/.env" ] || { echo "run '$0 setup' first"; exit 1; }
  set -a; . "$LIVE/.env"; set +a
  # the tunnel makes this server public: never without the token and the proxy check
  [ -n "${TERRATRIAGE_TOKEN:-}" ] || { echo "TERRATRIAGE_TOKEN missing in $LIVE/.env"; exit 1; }
  [ -n "${NCR_PROXY_SECRET:-}" ] || { echo "NCR_PROXY_SECRET missing in $LIVE/.env"; exit 1; }
  [ "${NCR_DEV_OPEN:-}" != "1" ] || { echo "NCR_DEV_OPEN=1 must never be public"; exit 1; }
}

alive() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }

case "${1:-}" in
setup)
  mkdir -p "$LIVE/data/output/ops" "$LIVE/data/labels" "$LIVE/data/truth" "$LIVE/data/cache" "$RUN" "$LIVE/site"
  chmod 700 "$LIVE"
  # a copy of the assessments, so this server never shares a data folder with a dev server
  if [ ! -f "$LIVE/data/ops_registry.yaml" ]; then
    cp "$REPO/pipeline/data/ops_registry.yaml" "$LIVE/data/"
    cp -R "$REPO/pipeline/data/output/ops/." "$LIVE/data/output/ops/"
    echo "copied assessments from pipeline/data"
  fi
  if [ ! -f "$LIVE/.env" ]; then
    umask 077
    gen() { "$PY" -c "import secrets; print(secrets.token_urlsafe(32))"; }
    cat > "$LIVE/.env" <<EOF
# NC Recon on this computer. Keep private. The responder token goes into
# the app under Responder access; anyone with it sees building-level data.
TERRATRIAGE_TOKEN=$(gen)
NCR_OWNER_SECRET=$(gen)
NCR_PROXY_SECRET=$(gen)
NCR_CLIENT_IP_HEADER=x-nf-client-connection-ip
# optional: a Netlify personal access token lets 'start' redeploy by itself
NETLIFY_AUTH_TOKEN=
EOF
    echo "wrote $LIVE/.env (secrets; never commit or share it)"
  fi
  ;;
start)
  load_env
  mkdir -p "$RUN"
  if ! alive server; then
    cd "$REPO/pipeline"
    HOST=127.0.0.1 PORT=$PORT \
      NCR_OPS_REGISTRY="$LIVE/data/ops_registry.yaml" NCR_OPS_OUT="$LIVE/data/output/ops" \
      NCR_OPS_CACHE="$LIVE/data/cache" NCR_JOBS_FILE="$LIVE/data/jobs.json" \
      NCR_LABELS_DIR="$LIVE/data/labels" NCR_TRUTH_DIR="$LIVE/data/truth" NCR_AUDIT_LOG="$LIVE/data/audit.log" \
      NCR_RAW_DIR="$REPO/pipeline/data/raw" \
      nohup "$PY" server.py </dev/null >"$RUN/server.log" 2>&1 &
    echo $! >"$RUN/server.pid"
    cd "$REPO"
    # keep the Mac awake (on power) while the server runs
    nohup caffeinate -s -w "$(cat "$RUN/server.pid")" </dev/null >/dev/null 2>&1 &
  fi
  i=0; until curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; do
    i=$((i+1)); [ $i -lt 60 ] || { echo "server did not start: $RUN/server.log"; exit 1; }; sleep 1; done
  if ! alive tunnel; then
    : >"$RUN/tunnel.log"
    nohup cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" </dev/null >"$RUN/tunnel.log" 2>&1 &
    echo $! >"$RUN/tunnel.pid"
  fi
  i=0; URL=""; until [ -n "$URL" ]; do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$RUN/tunnel.log" | head -1 || true)
    i=$((i+1)); [ $i -lt 60 ] || { echo "tunnel did not start: $RUN/tunnel.log"; exit 1; }; sleep 1; done
  echo "$URL" >"$RUN/tunnel.url"
  "$PY" "$REPO/deploy/home/build_front.py" --api "$URL" --out "$LIVE/site" ${NCR_SKIP_BUILD:+--skip-build}
  if [ -n "${NETLIFY_AUTH_TOKEN:-}" ]; then
    (cd "$LIVE/site" && npx -y netlify-cli@23 deploy --prod --site "$SITE_ID" --dir dist --message "tunnel $URL")
  else
    echo "front end built in $LIVE/site; deploy it (README: 'Publishing the front end')"
  fi
  echo "live: server :$PORT, tunnel $URL"
  ;;
stop)
  for p in tunnel server; do
    if alive $p; then kill "$(cat "$RUN/$p.pid")" && echo "stopped $p"; fi
    rm -f "$RUN/$p.pid"
  done
  ;;
status)
  for p in server tunnel; do if alive $p; then echo "$p: running"; else echo "$p: stopped"; fi; done
  [ -f "$RUN/tunnel.url" ] && echo "tunnel: $(cat "$RUN/tunnel.url")"
  ;;
*)
  echo "usage: $0 setup|start|stop|status"; exit 2
  ;;
esac
