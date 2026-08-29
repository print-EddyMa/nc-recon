"""End-to-end: a pre/post GeoTIFF pair -> one contract GeoJSON of damage-classified
building footprints.

    pre.tif, post.tif
        |  geo.iter_tiles           1024px chips + per-tile affine transform
        v
    Ensemble.predict_tile          loc prob (H,W) + cls prob (H,W,5)   [+TTA]
        |  geo.MaskCanvas           feather-blended stitch back to full raster
        v
    ensemble.fuse                   reference loc/cls fusion -> loc + damage masks
        |  geo.polygonize           connected components -> simplified polygons,
        v                           majority damage class, reprojected to lon/lat
    contract.collection            FeatureCollection + run metadata
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import numpy as np
from tqdm import tqdm

from . import contract
from .geo import iter_tiles, raster_grid, MaskCanvas, polygonize


def run(
    pre_path: str,
    post_path: str,
    out_path: str,
    *,
    event: str,
    area: str,
    weights_dir: str | None = None,
    preset: str = "fast",
    device: str = "cpu",
    tile: int = 1024,
    overlap: int = 128,
    loc_thr: float = 0.35,
    min_area_px: int = 14,
    pre_meta: dict | None = None,
    post_meta: dict | None = None,
    limit_tiles: int | None = None,
    mock: bool = False,
) -> dict[str, Any]:
    t0 = time.time()

    if mock or not weights_dir:
        from .models.mock import MockEnsemble
        model = MockEnsemble()
        model_name = MockEnsemble.name
        if not mock:
            print("[predict] no weights_dir given -> running heuristic MockEnsemble")
    else:
        from .models import ensemble as ens
        model = ens.build(weights_dir, preset=preset, device=device)
        model_name = f"xview2_1st_place:{preset} (loc x{len(model.loc)}, cls x{len(model.cls)})"

    from .models.ensemble import fuse

    H, W, transform, crs, bounds_lonlat = raster_grid(pre_path, post_path)
    print(f"[predict] raster {W}x{H} px, CRS {crs}, model={model_name}")

    loc_canvas = MaskCanvas(H, W, 1)
    dmg_canvas = MaskCanvas(H, W, 4)   # accumulate cls channels 1..4 as float

    tile_iter = iter_tiles(pre_path, post_path, tile=tile, overlap=overlap)
    if limit_tiles:
        import itertools

        tiles = list(itertools.islice(tile_iter, limit_tiles))
    else:
        tiles = list(tile_iter)
    print(f"[predict] {len(tiles)} tiles")

    for t in tqdm(tiles, desc="inference"):
        loc_prob, cls_prob = model.predict_tile(t.pre, t.post)
        loc_canvas.add(t, loc_prob.astype("float32"))
        dmg_canvas.add(t, cls_prob[..., 1:].astype("float32"))

    loc_full = loc_canvas.result()                    # (H,W)
    dmg_full = dmg_canvas.result()                    # (H,W,4)
    # rebuild a 5-channel cls_prob so `fuse` sees the same shape as per-tile
    cls_full = np.concatenate([(1.0 - loc_full)[..., None], dmg_full], axis=2)

    loc_mask, dmg_mask, dmg_conf = fuse(loc_full, cls_full)

    features_raw, records = polygonize(
        loc_mask.astype("float32"), dmg_mask, dmg_conf,
        transform, crs, loc_thr=loc_thr, min_area_px=min_area_px, area_prefix=area,
    )
    features = [
        contract.feature(f"{area}-{i:06d}", ring, dc, conf, area_m2, cen)
        for i, (_, ring, dc, conf, area_m2, cen) in enumerate(features_raw)
    ]

    meta = contract.RunMeta(
        event=event,
        area=area,
        model=model_name,
        pre_image=contract.ImageMeta(**(pre_meta or {"date": "unknown"})),
        post_image=contract.ImageMeta(**(post_meta or {"date": "unknown"})),
        tile_size=tile,
        notes=None if (weights_dir and not mock) else
        "Damage from a change-detection heuristic, NOT the xView2 CNN. For pipeline/UI bring-up.",
    )
    fc = contract.collection(features, meta)
    fc["properties"]["bounds"] = [round(b, 6) for b in bounds_lonlat]
    fc["properties"]["runtime_sec"] = round(time.time() - t0, 1)

    problems = contract.validate(fc)
    if problems:
        print(f"[predict] WARNING: {len(problems)} contract issue(s): {problems[:3]}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(fc, fh)
    print(f"[predict] wrote {out_path}  ({len(features)} buildings, "
          f"{fc['properties']['counts']}, {fc['properties']['runtime_sec']}s)")
    return fc
