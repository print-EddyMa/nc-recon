"""Web-map tiles cut on demand from an area's stored before / after imagery.

The Operations map shows structures over the exact imagery the assessment
read, so an analyst reviews a call against its own evidence rather than
against a third-party basemap of unknown date.

Tiles are standard 256 px XYZ / Web Mercator. Nothing is measured on them (the
assessment works in the imagery's own projected CRS); Web Mercator is only how
a slippy map asks for pictures. Each tile is rendered once and kept under
data/cache/ops/tiles, keyed by the source file's modification time, so a
re-fetched area never shows a stale tile.
"""
from __future__ import annotations

import io
import os

from .. import OPS_CACHE

TILE = 256
MIN_ZOOM = 12   # one tile already spans a whole AOI well before this
MAX_ZOOM = 19   # ~0.24 m / px at NC latitudes, the stored 0.3 m grid; the map upsamples past it
                # (deeper levels would only multiply the cache: tiles quadruple per level)


def tile_dir(area: str, kind: str, src_path: str) -> str:
    stamp = int(os.path.getmtime(src_path))
    return os.path.join(OPS_CACHE, "tiles", area, f"{kind}-{stamp}")


def render(src_path: str, z: int, x: int, y: int) -> tuple[bytes, str] | None:
    """One tile as (bytes, media type), or None when it lies wholly outside the
    image. Fully covered tiles are JPEG; edge tiles are PNG with transparency
    so the basemap shows through where there is no imagery."""
    import mercantile
    import numpy as np
    import rasterio
    from affine import Affine
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import Window
    from rasterio.windows import from_bounds as window_from_bounds
    from rasterio.windows import transform as window_transform

    b = mercantile.xy_bounds(x, y, z)
    with rasterio.open(src_path) as ds:
        left, bottom, right, top = transform_bounds("EPSG:3857", ds.crs, b.left, b.bottom, b.right, b.top,
                                                    densify_pts=21)
        # the part of the image under this tile, padded so bilinear resampling
        # has neighbours at the tile edge
        win = window_from_bounds(left, bottom, right, top, ds.transform)
        pad = 2
        c0 = max(0, int(np.floor(win.col_off)) - pad)
        r0 = max(0, int(np.floor(win.row_off)) - pad)
        c1 = min(ds.width, int(np.ceil(win.col_off + win.width)) + pad)
        r1 = min(ds.height, int(np.ceil(win.row_off + win.height)) + pad)
        if c1 <= c0 or r1 <= r0:
            return None
        win = Window(c0, r0, c1 - c0, r1 - r0)
        # read no finer than the tile needs: at low zoom a tile covers
        # thousands of source pixels, and averaging them on read is far cheaper
        # than warping them all
        src_px_per_tile_px = ((right - left) / abs(ds.transform.a)) / TILE
        dec = max(1, int(src_px_per_tile_px))
        h, w = max(1, int(round(win.height / dec))), max(1, int(round(win.width / dec)))
        bands = [1, 2, 3] if ds.count >= 3 else [1, 1, 1]
        src = ds.read(indexes=bands, window=win, out_shape=(3, h, w), resampling=Resampling.average)
        valid = ds.read_masks(1, window=win, out_shape=(h, w), resampling=Resampling.nearest)
        t = window_transform(win, ds.transform)
        src_transform = t @ Affine.scale(win.width / w, win.height / h)
        src_crs = ds.crs
    dst_transform = from_bounds(b.left, b.bottom, b.right, b.top, TILE, TILE)
    rgb = np.zeros((3, TILE, TILE), dtype="uint8")
    alpha = np.zeros((TILE, TILE), dtype="uint8")
    reproject(src, rgb, src_transform=src_transform, src_crs=src_crs, dst_transform=dst_transform,
              dst_crs="EPSG:3857", resampling=Resampling.bilinear)
    reproject(valid, alpha, src_transform=src_transform, src_crs=src_crs, dst_transform=dst_transform,
              dst_crs="EPSG:3857", resampling=Resampling.nearest)
    if not alpha.any():
        return None
    buf = io.BytesIO()
    if alpha.all():
        Image.fromarray(np.transpose(rgb, (1, 2, 0))).save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    rgba = np.concatenate([rgb, alpha[None]], axis=0)
    Image.fromarray(np.transpose(rgba, (1, 2, 0)), mode="RGBA").save(buf, format="PNG")
    return buf.getvalue(), "image/png"


def get(area: str, kind: str, src_path: str, z: int, x: int, y: int) -> tuple[bytes, str] | None:
    """Cached `render`. An empty file on disk records "outside the image"."""
    d = os.path.join(tile_dir(area, kind, src_path), str(z), str(x))
    for ext, media in (("jpg", "image/jpeg"), ("png", "image/png")):
        p = os.path.join(d, f"{y}.{ext}")
        if os.path.exists(p):
            with open(p, "rb") as fh:
                body = fh.read()
            return (body, media) if body else None
    out = render(src_path, z, x, y)
    try:
        os.makedirs(d, exist_ok=True)
        ext = "jpg" if out is None or out[1] == "image/jpeg" else "png"
        tmp = os.path.join(d, f"{y}.{ext}.{os.getpid()}.tmp")
        with open(tmp, "wb") as fh:
            fh.write(out[0] if out else b"")
        os.replace(tmp, os.path.join(d, f"{y}.{ext}"))
    except OSError as ex:  # a full or read-only cache must not cost the tile
        print(f"[tiles] cache write failed: {ex}")
    return out
