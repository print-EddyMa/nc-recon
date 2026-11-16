"""Getting "where" right before "what".

CRS registry, a single transform helper, datum-realization offsets, USNG, and
guards against the classic mistakes (axis order, US survey foot vs. international
foot, measuring in Web Mercator).

Rules enforced here:
  * every Transformer is built with always_xy=True (lon/lat, easting/northing)
  * distances and areas are never computed in EPSG:3857
  * the canonical storage/exchange frame is EPSG:4326 lon/lat (RFC 7946)
  * statewide metric work is EPSG:6542, per-tile metric work is the point's
    NAD83(2011) UTM zone (17N/18N in NC), equal-area statistics are EPSG:5070

CRS choices come from `config/crs.yaml` when present so the NSRS 2022 frames
(NATRF2022 / SPCS2022) can be swapped in by config, not by code edits.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache

from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup

from . import CONFIG_DIR

# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
DEFAULT_REGISTRY: dict[str, int] = {
    "storage": 4326,          # WGS 84 lon/lat (GeoJSON RFC 7946)
    "nc_geographic": 6318,    # NAD83(2011)
    "nc_geographic_3d": 6319, # NAD83(2011) with ellipsoidal height
    "nc_metric": 6542,        # NAD83(2011) / North Carolina (m)
    "nc_ftus": 6543,          # NAD83(2011) / North Carolina (ftUS)
    "nc_legacy_m": 32119,     # NAD83 / North Carolina (m)
    "nc_legacy_ftus": 2264,   # NAD83 / North Carolina (ftUS)
    "nc_harn": 3358,          # NAD83(HARN) / North Carolina
    "utm17": 6346,            # NAD83(2011) / UTM 17N (west of 78W)
    "utm18": 6347,            # NAD83(2011) / UTM 18N
    "equal_area": 5070,       # NAD83 / Conus Albers
    "navd88_m": 5703,
    "navd88_ftus": 6360,
    "wgs84_g2139": 9755,
    "wgs84_g2139_3d": 9754,
    "itrf2014_3d": 7912,
    "display": 3857,          # Web Mercator: display only
}
NO_MEASURE = {3857, 900913, 3785}
NC_BBOX = (-84.33, 33.84, -75.46, 36.59)  # tight state bbox (lon/lat)


@lru_cache(maxsize=1)
def registry() -> dict[str, int]:
    reg = dict(DEFAULT_REGISTRY)
    path = os.path.join(CONFIG_DIR, "crs.yaml")
    if os.path.exists(path):
        import yaml

        with open(path, encoding="utf-8") as fh:
            over = yaml.safe_load(fh) or {}
        for k, v in (over.get("crs") or {}).items():
            if v is not None:
                reg[k] = int(v)
    return reg


def crs(role) -> CRS:
    """A registry role name ("nc_metric"), an EPSG int, or anything pyproj.CRS takes."""
    if isinstance(role, CRS):
        return role
    if isinstance(role, int):
        return CRS.from_epsg(role)
    if isinstance(role, str) and role in registry():
        return CRS.from_epsg(registry()[role])
    return CRS(role)


@lru_cache(maxsize=64)
def _transformer(src_wkt: str, dst_wkt: str) -> Transformer:
    return Transformer.from_crs(CRS(src_wkt), CRS(dst_wkt), always_xy=True)


def transformer(src, dst) -> Transformer:
    """The one way to build a Transformer in this codebase (always_xy)."""
    return _transformer(crs(src).to_wkt(), crs(dst).to_wkt())


def _epsg(c) -> int | None:
    try:
        return CRS(c).to_epsg()
    except Exception:  # noqa: BLE001
        return None


def assert_measurable(c) -> None:
    """Refuse length/area math in Web Mercator (x1.23 lengths, x1.51 areas at 35.6N)."""
    if _epsg(c) in NO_MEASURE:
        raise ValueError(
            "refusing to measure in Web Mercator (EPSG:3857): use EPSG:6542 "
            "(statewide), UTM (per-tile) or EPSG:5070 (areas)"
        )
    cc = CRS(c)
    if cc.is_geographic:
        raise ValueError(f"refusing to measure in a geographic CRS ({cc.name}); project first")


def utm_for(lon: float, lat: float = 1.0) -> int:
    """NAD83(2011) UTM zone EPSG for a longitude (17N west of 78W in NC).

    NAD83(2011) defines UTM 1N-19N as EPSG 6330-6348 (the US and its
    territories north of the equator); anywhere else falls back to WGS 84 UTM.
    Zones 17 and 18 come from the registry so config can swap NSRS frames.
    """
    zone = min(60, int((lon + 180.0) // 6) + 1)
    if zone == 17 and lat >= 0:
        return registry()["utm17"]
    if zone == 18 and lat >= 0:
        return registry()["utm18"]
    if 1 <= zone <= 19 and lat >= 0:
        return 6329 + zone
    return (32600 if lat >= 0 else 32700) + zone


def in_nc(lon: float, lat: float, pad: float = 0.0) -> bool:
    w, s, e, n = NC_BBOX
    return (w - pad) <= lon <= (e + pad) and (s - pad) <= lat <= (n + pad)


US_BBOXES = (
    (-125.0, 24.0, -66.5, 49.6),    # contiguous states
    (-180.0, 51.0, -129.0, 71.6),   # Alaska
    (-161.0, 18.5, -154.0, 22.6),   # Hawaii
    (-68.2, 17.5, -64.3, 18.7),     # Puerto Rico and US Virgin Islands
)


def in_us(lon: float, lat: float, pad: float = 0.0) -> bool:
    return any((w - pad) <= lon <= (e + pad) and (s - pad) <= lat <= (n + pad)
               for w, s, e, n in US_BBOXES)


def assert_lonlat_in_us(lon: float, lat: float) -> None:
    """Axis-order guard for any US point: a swapped pair lands far outside."""
    if not in_us(lon, lat, pad=0.5):
        if in_us(lat, lon, pad=0.5):
            raise ValueError(f"({lon}, {lat}) looks like (lat, lon): axis order swapped")
        raise ValueError(f"({lon}, {lat}) is not in the United States")


def assert_lonlat_in_nc(lon: float, lat: float) -> None:
    """Axis-order guard: an NC point with lat/lon swapped lands in Antarctica."""
    if not in_nc(lon, lat, pad=0.5):
        if in_nc(lat, lon, pad=0.5):
            raise ValueError(f"({lon}, {lat}) looks like (lat, lon): axis order swapped")
        raise ValueError(f"({lon}, {lat}) is not in North Carolina")


def area_m2(geom_lonlat) -> float:
    """Equal-area (EPSG:5070) area of a lon/lat shapely geometry."""
    from shapely.ops import transform as st

    return st(transformer("storage", "equal_area").transform, geom_lonlat).area


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Geodesic distance on the GRS80/WGS84 ellipsoid (sub-mm agreement)."""
    from pyproj import Geod

    return Geod(ellps="GRS80").inv(lon1, lat1, lon2, lat2)[2]


# --------------------------------------------------------------------------- #
# datum realizations
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DatumOffset:
    horizontal_m: float
    vertical_m: float
    east_m: float
    north_m: float
    operation: str


def nad83_2011_to_itrf2014(lon: float, lat: float, h: float, epoch: float) -> DatumOffset:
    """Time-dependent NAD83(2011) -> ITRF2014 offset at a point.

    NAD83(2011) is plate-fixed (epoch 2010.00); ITRF2014 moves with the North
    American plate (~2 cm/yr in NC), so the gap grows with time. PROJ carries
    the published 14-parameter Helmert; this refuses a ballpark (null) operation.
    """
    tg = TransformerGroup(registry()["nc_geographic_3d"], registry()["itrf2014_3d"], always_xy=True)
    if not tg.transformers:
        raise RuntimeError("no NAD83(2011)->ITRF2014 operation available in PROJ")
    t = tg.transformers[0]
    if "ballpark" in t.description.lower():
        raise RuntimeError(f"PROJ offered only a ballpark transform: {t.description}")
    x, y, z, _ = t.transform(lon, lat, h, epoch)
    dn = (y - lat) * _m_per_deg_lat(lat)
    de = (x - lon) * _m_per_deg_lon(lat)
    return DatumOffset(math.hypot(de, dn), z - h, de, dn, t.description)


def _m_per_deg_lat(lat: float) -> float:
    p = math.radians(lat)
    return 111132.954 - 559.822 * math.cos(2 * p) + 1.175 * math.cos(4 * p)


def _m_per_deg_lon(lat: float) -> float:
    a, e2 = 6378137.0, 0.00669438
    p = math.radians(lat)
    return math.pi * a * math.cos(p) / (180 * math.sqrt(1 - e2 * math.sin(p) ** 2))


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #
US_SURVEY_FOOT_M = 1200.0 / 3937.0   # 0.3048006096...
INTL_FOOT_M = 0.3048


def ftus_to_m(v: float) -> float:
    return v * US_SURVEY_FOOT_M


def ft_to_m(v: float) -> float:
    return v * INTL_FOOT_M


def crs_linear_unit(c) -> str:
    """'metre' / 'US survey foot' / 'foot' for a projected CRS."""
    cc = CRS(c)
    ax = cc.axis_info[0]
    return ax.unit_name


# --------------------------------------------------------------------------- #
# USNG (US National Grid)
# --------------------------------------------------------------------------- #
def usng(lon: float, lat: float, precision_m: int = 1) -> str:
    """USNG string at 1 / 10 / 100 m precision, e.g. '17S LV 12345 67890'.

    USNG is MGRS on the NAD83 / WGS 84 ellipsoid; at the 1 m level the ~1 m
    NAD83(2011)-vs-WGS 84 realization gap is below what the grid string can
    express reliably, so the input is treated as NAD83(2011) lon/lat and the
    string is documented as such in exports. The `mgrs` library computes on
    WGS 84 (identical ellipsoid parameters to GRS80 to 0.1 mm).
    """
    import mgrs

    digits = {1: 5, 10: 4, 100: 3, 1000: 2}[precision_m]
    raw = mgrs.MGRS().toMGRS(lat, lon, MGRSPrecision=digits)
    raw = raw.decode() if isinstance(raw, bytes) else raw
    gzd, sq, rest = raw[:3], raw[3:5], raw[5:]
    half = len(rest) // 2
    return f"{gzd} {sq} {rest[:half]} {rest[half:]}"


def usng_to_lonlat(s: str) -> tuple[float, float]:
    """Parse a USNG/MGRS string (spaces optional) to (lon, lat) of the cell SW corner."""
    import mgrs

    lat, lon = mgrs.MGRS().toLatLon("".join(s.split()).upper())
    return lon, lat
