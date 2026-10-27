"""Per-building image evidence: masks (E-context), pixel change (E2), tarps (E4).

For each footprint we read a chip from the pre and post images (native 0.3 m
ARD grid), align post to pre locally, match radiometry, and measure inside the
footprint (eroded by one pixel) and in a debris ring around it.

Everything returned is a *measurement* with its quality and reason codes; turning
measurements into class likelihoods happens in `channels.py` using the
provisional mappings in config/context_rules.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds

from ..process import coreg

RING_M = 4.0


@dataclass
class BuildingEvidence:
    idx: int
    reasons: list[str] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)
    m: dict[str, Any] = field(default_factory=dict)  # measurements


def _hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(3,H,W) uint8 -> hue [0,360), sat [0,1], val [0,1]."""
    x = rgb.astype("float32") / 255.0
    r, g, b = x
    mx, mn = x.max(axis=0), x.min(axis=0)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rr = nz & (mx == r)
    gg = nz & (mx == g) & ~rr
    bb = nz & ~rr & ~gg
    h[rr] = (60 * ((g[rr] - b[rr]) / d[rr]) + 360) % 360
    h[gg] = 60 * ((b[gg] - r[gg]) / d[gg]) + 120
    h[bb] = 60 * ((r[bb] - g[bb]) / d[bb]) + 240
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def tarp_mask(rgb: np.ndarray) -> np.ndarray:
    """USACE/private blue-tarp colour: saturated mid-blue. Blue roofs and pools
    match too; the caller subtracts the pre-event blue fraction."""
    h, s, v = _hsv(rgb)
    return (h >= 195) & (h <= 235) & (s >= 0.35) & (v >= 0.30)


def cloud_mask(rgb: np.ndarray, bright_min: float, sat_max: float) -> np.ndarray:
    _, s, _ = _hsv(rgb)
    bright = rgb.min(axis=0) >= bright_min
    return bright & (s <= sat_max)


def exg_mask(rgb: np.ndarray, thr: float) -> np.ndarray:
    r, g, b = rgb.astype("float32")
    return (2 * g - r - b) > thr


def _gray(a: np.ndarray) -> np.ndarray:
    a = a.astype("float32")
    return 0.299 * a[0] + 0.587 * a[1] + 0.114 * a[2]


def aoi_radiometry(pre_path: str, post_path: str) -> tuple[np.ndarray, np.ndarray]:
    """AOI-wide post->pre gain/offset on a 1/8 overview (robust to damage)."""
    from rasterio.enums import Resampling

    with rasterio.open(pre_path) as a, rasterio.open(post_path) as b:
        h, w = a.height // 8, a.width // 8
        pa = a.read(out_shape=(3, h, w), resampling=Resampling.average)
        pb = b.read(out_shape=(3, h, w), resampling=Resampling.average)
    return coreg.radiometric_fit(pa, pb)


def measure(
    pre_path: str,
    post_path: str,
    polys_raster_crs: list,
    rules: dict[str, Any],
    gains: np.ndarray,
    offs: np.ndarray,
) -> list[BuildingEvidence]:
    from skimage.metrics import structural_similarity as ssim

    out: list[BuildingEvidence] = []
    cfg_c, cfg_v, cfg_n, cfg_r = rules["cloud"], rules["canopy"], rules["nodata"], rules["coreg"]
    with rasterio.open(pre_path) as a, rasterio.open(post_path) as b:
        res = abs(a.transform.a)
        max_px = cfg_r["max_local_shift_m"] / res
        pad = RING_M + cfg_r["max_local_shift_m"]
        for i, poly in enumerate(polys_raster_crs):
            ev = BuildingEvidence(i)
            minx, miny, maxx, maxy = poly.bounds
            win = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad, a.transform)
            win = win.round_offsets().round_lengths()
            win = Window(win.col_off, win.row_off, max(win.width, 16), max(win.height, 16))
            pre = a.read(indexes=[1, 2, 3], window=win, boundless=True, fill_value=0)
            post = b.read(indexes=[1, 2, 3], window=win, boundless=True, fill_value=0)
            tr = a.window_transform(win)
            shape = pre.shape[1:]
            fp = rasterize([(poly, 1)], out_shape=shape, transform=tr, fill=0, all_touched=False).astype(bool)
            if fp.sum() < 4:
                fp = rasterize([(poly, 1)], out_shape=shape, transform=tr, fill=0, all_touched=True).astype(bool)
            ring = rasterize([(poly.buffer(RING_M), 1)], out_shape=shape, transform=tr, fill=0).astype(bool) & ~fp
            from scipy.ndimage import binary_erosion

            core = binary_erosion(fp) if fp.sum() > 30 else fp
            n_fp = int(fp.sum())
            ev.m["footprint_px"] = n_fp

            # no-data (image edge)
            nod = ((pre.max(axis=0) == 0) | (post.max(axis=0) == 0))[fp].mean() if n_fp else 1.0
            ev.m["nodata_frac"] = round(float(nod), 3)
            if nod > cfg_n["unavailable_frac"]:
                ev.unavailable["E1"] = ev.unavailable["E2"] = ev.unavailable["E4"] = "IMAGE_NODATA"
                ev.reasons.append(f"IMAGE_NODATA_{nod * 100:.0f}PCT")
                out.append(ev)
                continue

            # cloud on the post image (footprint + ring)
            cm = cloud_mask(post, cfg_c["bright_min"], cfg_c["sat_max"])
            fr = fp | ring
            cf = float(cm[fr].mean())
            # a bright metal roof also trips the heuristic: only count "cloud"
            # where the pre image was NOT already equally bright
            pre_bright = cloud_mask(pre, cfg_c["bright_min"], cfg_c["sat_max"])
            cf_new = float((cm & ~pre_bright)[fr].mean())
            ev.m["cloud_frac_post"] = round(cf_new, 3)
            if cf_new > cfg_c["unavailable_frac"]:
                ev.unavailable["E1"] = ev.unavailable["E2"] = "POSSIBLE_CLOUD"
                ev.reasons.append(f"POSSIBLE_CLOUD_{cf_new * 100:.0f}PCT")

            # haze / thin cloud / cloud shadow: the bright-white test misses
            # these. Signature measured on Old Fort (Maxar post, 14% cloud):
            # post loses its colour AND its texture relative to pre. Both are
            # ratios to the pre image, so they carry across sensors.
            hz = rules.get("haze", {})
            _, s_pre, _ = _hsv(pre)
            _, s_post, _ = _hsv(post)
            valid = (pre.max(axis=0) > 0) & (post.max(axis=0) > 0)
            if valid.sum() > 50:
                sat_ratio = float(s_post[valid].mean() / max(s_pre[valid].mean(), 1e-3))
                tex_pre = float(np.hypot(*np.gradient(_gray(pre)))[valid].mean())
                tex_post = float(np.hypot(*np.gradient(_gray(post)))[valid].mean())
                tex_ratio = tex_post / max(tex_pre, 1e-3)
                ev.m["post_sat_ratio"] = round(sat_ratio, 3)
                ev.m["post_texture_ratio"] = round(tex_ratio, 3)
                if (sat_ratio < hz.get("max_sat_ratio", 0.5) and tex_ratio < hz.get("max_texture_ratio", 0.6)
                        and "E1" not in ev.unavailable):
                    ev.unavailable["E1"] = ev.unavailable["E2"] = "POSSIBLE_CLOUD_OR_HAZE"
                    ev.reasons.append(f"POSSIBLE_CLOUD_OR_HAZE_SAT{sat_ratio:.2f}_TEX{tex_ratio:.2f}")

            # canopy over roof (either date; leaf-on post usually larger)
            can = max(float(exg_mask(pre, cfg_v["exg_min"])[fp].mean()),
                      float(exg_mask(post, cfg_v["exg_min"])[fp].mean()))
            ev.m["canopy_frac"] = round(can, 3)
            if can > cfg_v["downweight_frac"]:
                ev.reasons.append(f"ROOF_UNDER_CANOPY_{can * 100:.0f}PCT")

            # local alignment + radiometric match
            gpre = _gray(pre)
            post_n = np.clip(post.astype("float32") * gains[:, None, None] + offs[:, None, None], 0, 255)
            gpost = _gray(post_n)
            dy, dx, nb, na = coreg.local_shift(gpre, gpost, max_px)
            ev.m["local_shift_m"] = [round(dy * res, 2), round(dx * res, 2)]
            ev.m["edge_ncc"] = round(na, 3)
            post_a = coreg.apply_shift(post_n, (dy, dx))
            gpost_a = _gray(post_a)

            # E2 measurements inside the footprint core and the ring
            if core.sum() >= 4 and "E2" not in ev.unavailable:
                s_full = ssim(gpre, gpost_a, data_range=255, full=True)[1]
                ssim_fp = float(s_full[core].mean())
                cva = np.linalg.norm(pre.astype("float32") - post_a, axis=0) / (255 * np.sqrt(3))
                cva_fp = float(cva[core].mean())
                cva_ring = float(cva[ring].mean()) if ring.any() else None
                ep = np.hypot(*np.gradient(gpre))
                eq = np.hypot(*np.gradient(gpost_a))
                e_scale = max(float(np.percentile(ep[fr], 95)), 1.0)
                edge_loss = float(np.clip((ep - eq) / e_scale, 0, 1)[core].mean())
                ev.m.update(ssim_fp=round(ssim_fp, 3), cva_fp=round(cva_fp, 3),
                            cva_ring=None if cva_ring is None else round(cva_ring, 3),
                            edge_loss=round(edge_loss, 3))
                pre_struct = float(np.percentile(ep[core], 75)) / e_scale
                ev.m["pre_structure"] = round(pre_struct, 3)
                if na < cfg_r["min_edge_ncc"] and pre_struct < 0.25:
                    # neither chip shows a crisp structure where the footprint
                    # says there is one: we cannot tell change from misalignment
                    ev.unavailable["E2"] = "MISREGISTERED"
                    ev.reasons.append("MISREGISTERED")

            # E4 tarps (post minus pre blue fraction on the roof)
            if "E4" not in ev.unavailable:
                t_post = float(tarp_mask(post)[fp].mean())
                t_pre = float(tarp_mask(pre)[fp].mean())
                ev.m["tarp_frac_post"] = round(t_post, 3)
                ev.m["tarp_frac_new"] = round(max(0.0, t_post - t_pre), 3)
            out.append(ev)
    return out


def change_score(m: dict[str, Any]) -> float | None:
    """Combine E2 measurements into one change score in [0, 1].

    Weights are provisional (see context_rules.yaml status). SSIM loss and
    edge loss carry the structural signal; CVA the spectral one; the ring adds
    debris around the footprint.
    """
    if "ssim_fp" not in m:
        return None
    s = (0.35 * (1 - max(m["ssim_fp"], 0.0))
         + 0.30 * min(1.0, m["edge_loss"] * 2.5)
         + 0.25 * min(1.0, m["cva_fp"] * 3.0)
         + 0.10 * min(1.0, (m.get("cva_ring") or 0.0) * 3.0))
    return float(np.clip(s, 0.0, 1.0))
