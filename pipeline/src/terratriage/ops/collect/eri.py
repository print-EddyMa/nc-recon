"""NOAA NGS Emergency Response Imagery (ERI) - post-event aerial orthos.

Bucket `noaa-eri-pds` (AWS Open Data, no credentials). Per event, one folder
per flight (`20240929a_RGB/`) of GeoTIFF tiles whose names encode the tile
centre, e.g. `20240929aC0823515w284930n.tif` = 82°35'15"W 28°49'30"N. So a
coverage index needs only the bucket listing, not the imagery.

Post-event only (15-30 cm). For change detection it must be paired with a
pre-event source (NC orthoimagery, NAIP); on its own it still supports
post-only evidence (E1 CNN, E4 tarps) and human review.
US Government work: credit NOAA NGS.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request

from ..provenance import Provenance
from .base import Connector, DiskCache, Layer, SchemaError, SourceUnavailable, USER_AGENT

BUCKET = "https://noaa-eri-pds.s3.amazonaws.com"
_NAME = re.compile(r"/(\d{8}[a-z])C(\d{3})(\d{2})(\d{2})w(\d{2})(\d{2})(\d{2})n\.tif$")


def parse_tile_name(key: str) -> dict | None:
    m = _NAME.search(key)
    if not m:
        return None
    flight, lod, lom, los, lad, lam, las = m.groups()
    return {
        "key": key, "flight": flight,
        "flight_date": f"{flight[:4]}-{flight[4:6]}-{flight[6:8]}",
        "lon": round(-(int(lod) + int(lom) / 60 + int(los) / 3600), 6),
        "lat": round(int(lad) + int(lam) / 60 + int(las) / 3600, 6),
    }


def _get(url: str, retries: int = 5) -> str:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                return r.read().decode()
        except Exception as ex:  # noqa: BLE001
            last = ex
            time.sleep(1.5 ** (i + 1))
    raise SourceUnavailable(f"ERI listing failed: {last}")


class ERI(Connector):
    name = "noaa_eri"
    license = "US Government work (NOAA NGS); public"
    homepage = "https://storms.ngs.noaa.gov/"
    stale_after_s = 10 * 365 * 86400

    def __init__(self) -> None:
        self.cache = DiskCache("eri")

    def index(self, event_prefix: str = "2024_Hurricane_Helene", refresh: bool = False) -> list[dict]:
        key = f"index_{event_prefix}"
        hit = None if refresh else self.cache.get(key)
        if hit is not None:
            return hit
        tiles, tok = [], None
        while True:
            q = {"list-type": "2", "prefix": f"{event_prefix}/2", "max-keys": "1000"}
            if tok:
                q["continuation-token"] = tok
            body = _get(f"{BUCKET}/?{urllib.parse.urlencode(q)}")
            for k, sz in re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", body):
                t = parse_tile_name(k)
                if t:
                    t["bytes"] = int(sz)
                    t["url"] = f"{BUCKET}/{k}"
                    tiles.append(t)
            m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
            if not m:
                break
            tok = m.group(1)
        if not tiles:
            raise SchemaError(f"no ERI tiles parsed under {event_prefix}")
        self.cache.put(key, tiles)
        return tiles

    def fetch(self, bbox_lonlat, event_prefix: str = "2024_Hurricane_Helene") -> Layer:
        w, s, e, n = bbox_lonlat
        tiles = [t for t in self.index(event_prefix) if w <= t["lon"] <= e and s <= t["lat"] <= n]
        prov = Provenance(source="NOAA NGS Emergency Response Imagery", source_url=f"{BUCKET}/{event_prefix}/",
                          license=self.license, crs="per tile (GeoTIFF)", horizontal_datum="per tile",
                          units="RGB uint8, ~15-30 cm GSD")
        return Layer(tiles, prov)

    def probe(self) -> float | None:
        body = _get(f"{BUCKET}/?list-type=2&prefix=2024_Hurricane_Helene/&delimiter=/&max-keys=5")
        if "<Prefix>" not in body:
            raise SchemaError("ERI probe: unexpected listing")
        return None
