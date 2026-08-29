"""Geo-referenced tiling, mask stitching, and polygonisation.

The whole point of this module: a model works in pixel space on 1024x1024 chips,
but the output has to land on a real map. Every Tile carries the affine transform
that maps its local pixels back to world coordinates, so a mask produced for a
chip can be turned into lon/lat polygons with no guesswork.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.transform import Affine, xy
from rasterio.warp import transform_geom
from shapely.geometry import shape, mapping, Polygon
from shapely.ops import transform as shapely_transform
from pyproj import Transformer


@dataclass
class Tile:
    """A 1024x1024 (or edge-clipped) chip plus everything needed to geo-place it."""

    col_off: int
    row_off: int
    width: int
    height: int
    transform: Affine          # local-pixel -> raster CRS (world units)
    crs: rasterio.crs.CRS      # raster CRS (e.g. EPSG:32617)
    pre: np.ndarray            # (H, W, 3) uint8 RGB
    post: np.ndarray           # (H, W, 3) uint8 RGB

    @property
    def key(self) -> str:
        return f"r{self.row_off:05d}_c{self.col_off:05d}"


def _read_rgb(ds, window: Window) -> np.ndarray:
    """Read a window as (H, W, 3) uint8. Handles 3- and 4-band (RGBA) sources."""
    arr = ds.read(indexes=[1, 2, 3], window=window, boundless=True, fill_value=0)
    return np.transpose(arr, (1, 2, 0)).astype("uint8")


def iter_tiles(
    pre_path: str,
    post_path: str,
    tile: int = 1024,
    overlap: int = 128,
    skip_blank: bool = True,
) -> Iterator[Tile]:
    """Yield aligned pre/post Tiles over the common footprint of two COGs.

    The two images are assumed to share a CRS and grid (Maxar ARD tiles do). We
    iterate the intersection of their pixel extents with a fixed stride so
    adjacent tiles overlap by `overlap` px; the overlap is averaged out at stitch
    time and keeps buildings on tile seams from being cut in half.
    """
    with rasterio.open(pre_path) as pre_ds, rasterio.open(post_path) as post_ds:
        if pre_ds.crs != post_ds.crs:
            raise ValueError(f"CRS mismatch: {pre_ds.crs} vs {post_ds.crs}")
        w = min(pre_ds.width, post_ds.width)
        h = min(pre_ds.height, post_ds.height)
        stride = tile - overlap
        for row_off in range(0, h, stride):
            for col_off in range(0, w, stride):
                tw = min(tile, w - col_off)
                th = min(tile, h - row_off)
                if tw <= 0 or th <= 0:
                    continue
                win = Window(col_off, row_off, tw, th)
                pre = _read_rgb(pre_ds, win)
                post = _read_rgb(post_ds, win)
                if skip_blank and (pre.max() == 0 or post.max() == 0):
                    continue
                yield Tile(
                    col_off=col_off,
                    row_off=row_off,
                    width=tw,
                    height=th,
                    transform=pre_ds.window_transform(win),
                    crs=pre_ds.crs,
                    pre=pre,
                    post=post,
                )


def raster_grid(pre_path: str, post_path: str) -> tuple[int, int, Affine, rasterio.crs.CRS, tuple]:
    """(height, width, transform, crs, bounds_lonlat) for the common footprint."""
    with rasterio.open(pre_path) as a, rasterio.open(post_path) as b:
        w = min(a.width, b.width)
        h = min(a.height, b.height)
        bounds = rasterio.coords.BoundingBox(
            a.bounds.left, a.transform.f + a.transform.e * h, a.transform.c + a.transform.a * w, a.bounds.top
        )
        tr = Transformer.from_crs(a.crs, 4326, always_xy=True)
        left, bottom = tr.transform(bounds.left, bounds.bottom)
        right, top = tr.transform(bounds.right, bounds.top)
        return h, w, a.transform, a.crs, (left, bottom, right, top)


class MaskCanvas:
    """Accumulates per-tile float masks into one full-raster mask with averaging."""

    def __init__(self, height: int, width: int, channels: int = 1):
        self.sum = np.zeros((height, width, channels), dtype="float32")
        self.wgt = np.zeros((height, width, 1), dtype="float32")
        self._feather = None

    def _window(self, t: Tile):
        return slice(t.row_off, t.row_off + t.height), slice(t.col_off, t.col_off + t.width)

    def add(self, t: Tile, mask: np.ndarray) -> None:
        """mask: (H, W) or (H, W, C) float. Cosine-feathered so seams blend."""
        if mask.ndim == 2:
            mask = mask[..., None]
        h, w = t.height, t.width
        fy = np.hanning(max(h, 3))[:, None] if h >= 3 else np.ones((h, 1))
        fx = np.hanning(max(w, 3))[None, :] if w >= 3 else np.ones((1, w))
        feather = np.clip(fy * fx, 1e-3, 1.0).astype("float32")[..., None]
        rs, cs = self._window(t)
        self.sum[rs, cs, :] += mask[:h, :w, :] * feather
        self.wgt[rs, cs, :] += feather

    def result(self) -> np.ndarray:
        out = self.sum / np.maximum(self.wgt, 1e-6)
        return out[..., 0] if out.shape[-1] == 1 else out


def polygonize(
    loc_mask: np.ndarray,
    dmg_mask: np.ndarray,
    dmg_prob: np.ndarray,
    transform: Affine,
    src_crs,
    *,
    loc_thr: float = 0.35,
    min_area_px: int = 12,
    simplify_m: float = 0.4,
    area_prefix: str = "b",
):
    """Turn stitched masks into contract Features.

    loc_mask : (H, W) float in [0,1]  building probability
    dmg_mask : (H, W) int   in 1..4   per-pixel damage class (xView2 numbering)
    dmg_prob : (H, W) float in [0,1]  per-pixel prob of the winning damage class
    Returns (features, records) where records is a list of dicts for QA.
    """
    from rasterio.features import shapes as rio_shapes
    from skimage.morphology import remove_small_objects, label as sk_label

    binary = (loc_mask >= loc_thr)
    binary = remove_small_objects(binary, min_size=min_area_px)
    labels = sk_label(binary, connectivity=2)

    utm_to_wgs = Transformer.from_crs(src_crs, 4326, always_xy=True).transform

    features, records = [], []
    idx = 0
    for geom, val in rio_shapes(labels.astype("int32"), mask=labels > 0, transform=transform):
        if val == 0:
            continue
        poly = shape(geom)
        if poly.is_empty or not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        # largest ring only; drop holes for the demo layer
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        area_m2 = poly.area  # src_crs is metric (UTM)
        if area_m2 < min_area_px * abs(transform.a) * abs(transform.e):
            continue
        poly_s = poly.simplify(simplify_m, preserve_topology=True)
        if poly_s.is_empty:
            poly_s = poly

        # pixel mask for this component -> majority damage class + mean prob
        comp = labels == int(val)
        dcls_vals = dmg_mask[comp]
        dcls_vals = dcls_vals[dcls_vals >= 1]
        if dcls_vals.size == 0:
            xv_class = 1
        else:
            xv_class = int(np.bincount(dcls_vals, minlength=5)[1:].argmax() + 1)
        conf = float(dmg_prob[comp & (dmg_mask == xv_class)].mean()) if np.any(comp & (dmg_mask == xv_class)) else float(dmg_prob[comp].mean())
        our_class = {1: 0, 2: 1, 3: 2, 4: 3}[xv_class]

        poly_wgs = shapely_transform(utm_to_wgs, poly_s)
        ring = [list(map(float, xy)) for xy in poly_wgs.exterior.coords]
        cen = poly_wgs.centroid

        features.append(
            (f"{area_prefix}-{idx:06d}", [ring], our_class, conf, area_m2, (cen.x, cen.y))
        )
        records.append({"id": idx, "damage_class": our_class, "area_m2": area_m2, "confidence": conf})
        idx += 1
    return features, records
