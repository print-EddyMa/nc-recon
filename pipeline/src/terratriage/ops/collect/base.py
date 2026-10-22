"""Connector contract.

Every data source is a `Connector` with:
  * `fetch(...)`  -> `Layer` (data + provenance), validated before it returns;
                    a schema failure raises `SchemaError` - it never degrades to
                    an empty layer that *looks like* "nothing happened"
  * `health()`    -> `Health` (status, latency, data age), for the collection
                    board and `make health`
  * polite HTTP: timeouts, retries with exponential backoff, 429/Retry-After
    handling, a real User-Agent, and an optional on-disk response cache
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .. import OPS_CACHE
from ..provenance import Provenance, utc_now

# Federal APIs (weather.gov in particular) ask for a User-Agent that names the
# application and a way to reach its operator. A deployment sets NCR_CONTACT
# (an email or URL); the project page is the fallback.
USER_AGENT = "NCRecon/2.0 (NC disaster damage decision support; {})".format(
    os.environ.get("NCR_CONTACT", "").strip() or "+https://github.com/print-EddyMa/nc-recon")


class SchemaError(ValueError):
    """Upstream returned something that does not match the connector contract."""


class SourceUnavailable(RuntimeError):
    """Upstream is down, moved, or needs credentials we do not have."""


@dataclass
class Layer:
    data: Any
    provenance: Provenance
    warnings: list[str] = field(default_factory=list)
    stale: bool = False


@dataclass
class Health:
    source: str
    status: str               # "ok" | "stale" | "down" | "unconfigured"
    latency_ms: float | None
    data_age_s: float | None
    detail: str = ""
    checked_utc: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def http_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    retries: int = 3,
    backoff: float = 1.5,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> Any:
    """GET/POST JSON with retries + exponential backoff; honours Retry-After."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe=",:$'")
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, application/geo+json"}
    hdrs.update(headers or {})
    key = os.environ.get("NCR_USGS_API_KEY") if "api.waterdata.usgs.gov" in url else None
    if key:
        hdrs["X-Api-Key"] = key
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                body = r.read()
            if body[:2] == b"\x1f\x8b":  # some servers gzip regardless of Accept-Encoding
                import gzip

                body = gzip.decompress(body)
            return json.loads(body)
        except urllib.error.HTTPError as ex:
            last = ex
            if ex.code in (400, 401, 403, 404):
                raise SourceUnavailable(f"{ex.code} from {url.split('?')[0]}") from ex
            wait = backoff ** (attempt + 1)
            if ex.code == 429:
                try:
                    wait = max(wait, float(ex.headers.get("Retry-After", wait)))
                except (TypeError, ValueError):
                    pass
            time.sleep(min(wait, 30))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as ex:
            last = ex
            time.sleep(min(backoff ** (attempt + 1), 30))
    raise SourceUnavailable(f"{url.split('?')[0]} failed after {retries} tries: {last}")


class DiskCache:
    """JSON response cache under data/cache/ops/<namespace>/<key>.json."""

    def __init__(self, namespace: str):
        self.dir = os.path.join(OPS_CACHE, namespace)
        os.makedirs(self.dir, exist_ok=True)

    def path(self, key: str) -> str:
        return os.path.join(self.dir, f"{key}.json")

    def get(self, key: str, max_age_s: float | None = None) -> Any | None:
        p = self.path(key)
        if not os.path.exists(p):
            return None
        if max_age_s is not None and time.time() - os.path.getmtime(p) > max_age_s:
            return None
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    def age_s(self, key: str) -> float | None:
        p = self.path(key)
        return time.time() - os.path.getmtime(p) if os.path.exists(p) else None

    def put(self, key: str, value: Any) -> None:
        tmp = self.path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(value, fh)
        os.replace(tmp, self.path(key))


def parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Connector:
    """Subclass and implement `fetch` and `probe` (a cheap live call for health)."""

    name = "base"
    license = "unknown"
    homepage = ""
    stale_after_s: float = 6 * 3600

    def fetch(self, **kw) -> Layer:  # pragma: no cover - interface
        raise NotImplementedError

    def probe(self) -> float | None:
        """Make one cheap live call; return data age in seconds (or None)."""
        raise NotImplementedError

    def configured(self) -> tuple[bool, str]:
        return True, ""

    def health(self) -> Health:
        ok, why = self.configured()
        if not ok:
            return Health(self.name, "unconfigured", None, None, why)
        t0 = time.time()
        try:
            age = self.probe()
        except Exception as ex:  # noqa: BLE001
            return Health(self.name, "down", round((time.time() - t0) * 1000), None, str(ex)[:300])
        lat = round((time.time() - t0) * 1000)
        status = "stale" if (age is not None and age > self.stale_after_s) else "ok"
        return Health(self.name, status, lat, None if age is None else round(age), "")
