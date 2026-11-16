"""Build the public front end for a home-hosted NC Recon (deploy/home/README.md).

    pipeline/.venv/bin/python deploy/home/build_front.py --api https://x.trycloudflare.com --out ~/ncrecon-live/site

Writes <out>/dist (the web app, built same-origin, with the launch page at
/about/) and <out>/netlify.toml, which proxies the API paths to the server on
this computer through the tunnel and adds the proxy secret header the server
checks (NCR_PROXY_SECRET). netlify.toml sits outside the published folder, so
the secret and the tunnel address are never served.

The app is built the way the Dockerfile builds it, and the same local-only
files the Docker build leaves out (.dockerignore) are left out here: imagery
tiles, building-level GeoJSON, the pitch demo and the intro.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WEB = os.path.join(ROOT, "web")
SITE = os.path.join(ROOT, "site")
sys.path.insert(0, os.path.join(ROOT, "pipeline", "src"))

# every top-level path the API answers on (pipeline/server.py and the /ops routers)
API_PATHS = ("/ops", "/areas", "/assess", "/catalog", "/events", "/feed", "/tiles", "/health")
# local-only material that must never be published (mirrors .dockerignore)
LOCAL_ONLY = ("tiles", "demo", "intro")


def build_app(dist: str) -> None:
    env = dict(os.environ, VITE_SAME_ORIGIN="1")
    env.pop("VITE_API_URL", None)
    subprocess.run([os.path.join(WEB, "node_modules", ".bin", "vite"), "build", "--outDir", dist, "--emptyOutDir"],
                   cwd=WEB, env=env, check=True, stdout=subprocess.DEVNULL)
    for name in LOCAL_ONLY:
        shutil.rmtree(os.path.join(dist, name), ignore_errors=True)
    data = os.path.join(dist, "data")
    for f in os.listdir(data) if os.path.isdir(data) else []:
        if f.endswith(".geojson"):                      # building-level calls stay private
            os.remove(os.path.join(data, f))


def add_about(dist: str) -> None:
    """The launch page (site/index.html), served at /about/."""
    about = os.path.join(dist, "about")
    os.makedirs(os.path.join(about, "assets"), exist_ok=True)
    shutil.copy(os.path.join(SITE, "index.html"), about)
    shutil.copy(os.path.join(SITE, "logo.svg"), about)
    shutil.copytree(os.path.join(SITE, "assets", "web"), os.path.join(about, "assets", "web"), dirs_exist_ok=True)


def write_headers(dist: str) -> None:
    from terratriage.ops import guard

    h = guard.security_headers(dist)
    csp = h.pop("Content-Security-Policy")
    lines = ["/*"] + [f"  {k}: {v}" for k, v in h.items()]
    # the app's strict policy goes on the app document only; /about/ is a
    # separate page with its own inline scripts and is not given it
    for path in ("/", "/index.html"):
        lines += [path, f"  Content-Security-Policy: {csp}"]
    with open(os.path.join(dist, "_headers"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def write_netlify_toml(out: str, api: str, secret: str) -> None:
    api = api.rstrip("/")
    rules = []
    for p in API_PATHS:
        for frm, to in ((p, f"{api}{p}"), (f"{p}/*", f"{api}{p}/:splat")):
            rules.append(f'[[redirects]]\n  from = "{frm}"\n  to = "{to}"\n  status = 200\n  force = true\n'
                         f'  headers = {{X-Ncr-Proxy = "{secret}"}}\n')
    rules.append('[[redirects]]\n  from = "/about"\n  to = "/about/"\n  status = 301\n')
    toml = '[build]\n  publish = "dist"\n  command = ""\n\n' + "\n".join(rules)
    path = os.path.join(out, "netlify.toml")
    with open(path, "w") as fh:
        fh.write(toml)
    os.chmod(path, 0o600)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="public tunnel URL of the server on this computer")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-build", action="store_true", help="reuse <out>/dist; only rewrite netlify.toml")
    a = ap.parse_args()
    secret = os.environ.get("NCR_PROXY_SECRET", "").strip()
    if not secret:
        sys.exit("NCR_PROXY_SECRET is not set: refusing to publish a proxy the server would not check")
    out = os.path.expanduser(a.out)
    dist = os.path.join(out, "dist")
    os.makedirs(out, exist_ok=True)
    if not a.skip_build or not os.path.isdir(dist):
        build_app(dist)
        add_about(dist)
        write_headers(dist)
    write_netlify_toml(out, a.api, secret)
    leaks = [os.path.join(r, f) for r, _, fs in os.walk(dist) for f in fs if f.endswith(".geojson")
             and os.path.basename(r) == "data"]
    if leaks:
        sys.exit(f"building-level files would be published: {leaks}")
    print(f"front end ready in {out} (API {a.api})")


if __name__ == "__main__":
    main()
