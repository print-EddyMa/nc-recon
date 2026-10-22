"""Request guards for the public surface: per-client rate limits and browser
security headers (including a Content Security Policy derived from the built
web app). Pure functions plus one small in-process limiter; no third-party
middleware, so behaviour is the same in tests and in the container.

Limits are per client address. Behind the bundled Caddy proxy every request
arrives from the proxy, so the proxy's `X-Forwarded-For` is used only when
`NCR_TRUST_PROXY=1` (set by docker-compose); anywhere else the header is
ignored, because a client could forge it.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import threading
import time
from collections import deque

# requests per minute, per client; writes are the expensive, audited routes
WRITE_PER_MIN = int(os.environ.get("NCR_RATE_WRITE_PER_MIN", "30"))
READ_PER_MIN = int(os.environ.get("NCR_RATE_READ_PER_MIN", "600"))
FEED_PER_MIN = int(os.environ.get("NCR_RATE_FEED_PER_MIN", "120"))
# routes that make this server call outside services on the client's behalf
# (imagery catalogs, a 15-20 MB photo download): cheap to ask for, expensive to
# answer, and the upstreams may block us if we relay a flood
UPSTREAM_PER_MIN = int(os.environ.get("NCR_RATE_UPSTREAM_PER_MIN", "30"))
WINDOW_S = 60.0
EXEMPT_PATHS = ("/health",)


def trust_proxy() -> bool:
    return os.environ.get("NCR_TRUST_PROXY", "").strip() == "1"


def client_ip(request) -> str:
    """Peer address, or the first `X-Forwarded-For` hop when the deployment
    says the proxy in front of us is trusted."""
    if trust_proxy():
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip() or "unknown"
    client = getattr(request, "client", None)
    return (client.host if client and client.host else "unknown")


class RateLimiter:
    """Sliding-window counter per key. `hit()` returns 0 when the request may
    proceed, else the number of seconds until the window has room again."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def hit(self, key: str, limit: int, now: float | None = None) -> float:
        if limit <= 0:
            return 0.0
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            cutoff = now - WINDOW_S
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                return max(0.1, q[0] + WINDOW_S - now)
            q.append(now)
            if now - self._last_sweep > WINDOW_S:  # forget idle clients
                self._last_sweep = now
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = RateLimiter()


def _upstream(path: str) -> bool:
    return path == "/ops/coverage" or (path.startswith("/ops/photos/") and "/thumb/" in path)


def limit_for(method: str, path: str) -> tuple[str, int]:
    """(bucket, requests per minute) for a request. One bucket per class so a
    burst of map reads cannot lock an analyst out of submitting a label."""
    if _upstream(path):
        return "upstream", UPSTREAM_PER_MIN
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "write", WRITE_PER_MIN
    if path.startswith("/feed/"):
        return "feed", FEED_PER_MIN
    return "read", READ_PER_MIN


def check(request) -> float:
    """0 if allowed, else seconds to wait (the caller answers 429)."""
    path = request.url.path
    if path in EXEMPT_PATHS or request.method == "OPTIONS":
        return 0.0
    bucket, limit = limit_for(request.method, path)
    return LIMITER.hit(f"{bucket}:{client_ip(request)}", limit)


# --------------------------------------------------------------------------- #
# CSV output hygiene
# --------------------------------------------------------------------------- #
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(v):
    """A value safe to put in a CSV that someone will open in a spreadsheet.

    A text cell starting with = + - @ (or a tab / carriage return) is run as a
    formula by Excel, LibreOffice and Google Sheets ("CSV injection"): a label
    note or an address read from a third-party layer could otherwise execute
    on an analyst's machine. Such cells get a leading apostrophe (OWASP's
    recommendation); numbers and other types pass through unchanged, and so
    does a string that is just a number ("-82.4012" in a coordinate column is
    a number to a spreadsheet, never a formula, and GIS imports need it as is)."""
    if isinstance(v, str) and v.startswith(_FORMULA_START):
        try:
            float(v)
            return v
        except ValueError:
            return "'" + v
    return v


# --------------------------------------------------------------------------- #
# security headers
# --------------------------------------------------------------------------- #
_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)

# Upstreams the browser talks to directly (basemap, radar, feeds that allow
# CORS). Anything else the app needs goes through /feed on this origin.
# Operators add hosts with NCR_CSP_CONNECT="https://host1 https://host2".
_CONNECT = [
    "'self'",
    "blob:",
    "data:",
    "https://basemaps.cartocdn.com",
    "https://*.basemaps.cartocdn.com",
    "https://api.weather.gov",
    "https://api.waterdata.usgs.gov",
    "https://waterdata.usgs.gov",
    "https://api.water.noaa.gov",
    "https://water.noaa.gov",
    "https://mesonet.agron.iastate.edu",
    "https://firms.modaps.eosdis.nasa.gov",
    "https://api.climate.ncsu.edu",
    "https://www.fema.gov",
    # AWS Terrain Tiles (terrarium elevation PNGs) for the optional 3-D terrain;
    # MapLibre fetches raster-dem from a worker, so it is a connect-src. Scoped
    # to the bucket path: a bare s3.amazonaws.com would admit every bucket
    "https://s3.amazonaws.com/elevation-tiles-prod/",
]


def inline_script_hashes(web_dist: str | None) -> list[str]:
    """CSP hashes for the inline scripts in the built index.html (the theme
    bootstrap), so the policy can forbid every other inline script."""
    if not web_dist:
        return []
    path = os.path.join(web_dist, "index.html")
    try:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
    except OSError:
        return []
    out = []
    for body in _INLINE_SCRIPT_RE.findall(html):
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        out.append("'sha256-" + base64.b64encode(digest).decode() + "'")
    return out


def offline() -> bool:
    return os.environ.get("NCR_OFFLINE", "").strip() == "1"


# routes that cannot work without a network: refused at once in offline mode
# instead of hanging on upstream timeouts
_NEEDS_NETWORK = (("POST", "/ops/assess"), ("POST", "/ops/events"), ("GET", "/ops/coverage"),
                  ("GET", "/ops/areas/*/fema-assistance"), ("POST", "/ops/areas/*/reassess"),
                  ("POST", "/ops/areas/*/response"), ("GET", "/feed/"))


def needs_network(method: str, path: str) -> bool:
    """True when the server is offline and this route would need the network."""
    if not offline():
        return False
    for m, pat in _NEEDS_NETWORK:
        if method != m:
            continue
        if pat.endswith("/") and path.startswith(pat):
            return True
        if "*" in pat:
            head, tail = pat.split("*", 1)
            if path.startswith(head) and path.endswith(tail) and "/" not in path[len(head):-len(tail) or None]:
                return True
        elif path == pat or path.startswith(pat + "/"):
            return True
    return False


def csp(web_dist: str | None) -> str:
    extra = os.environ.get("NCR_CSP_CONNECT", "").split()
    # offline: the page may reach this server and nothing else, so a missed
    # external URL fails loudly instead of leaking a request or hanging
    connect = "'self' blob: data:" if offline() else " ".join(_CONNECT + extra)
    script = " ".join(["'self'"] + inline_script_hashes(web_dist))
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "img-src 'self' data: blob:" + ("" if offline() else " https:"),
        f"connect-src {connect}",
        "worker-src 'self' blob:",
        "child-src blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


def security_headers(web_dist: str | None) -> dict[str, str]:
    return {
        "Content-Security-Policy": csp(web_dist),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(self), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
