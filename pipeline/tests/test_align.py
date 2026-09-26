import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from terratriage.ops.process import align


def _scene(tmp_path, shift=(3.0, -2.1)):
    rng = np.random.default_rng(0)
    res, n = 0.3, 1500
    img = np.full((3, n, n), 90, "uint8")
    x0, y1 = 400000.0, 3950000.0
    polys = []
    for _ in range(60):
        cx, cy = rng.uniform(40, n * res - 40, 2)
        w, h = rng.uniform(8, 16, 2)
        p = box(x0 + cx - w / 2, y1 - cy - h / 2, x0 + cx + w / 2, y1 - cy + h / 2)
        # draw the *true* roof shifted by `shift` from the footprint
        c0 = int((p.bounds[0] + shift[0] - x0) / res); c1 = int((p.bounds[2] + shift[0] - x0) / res)
        r0 = int((y1 - (p.bounds[3] + shift[1])) / res); r1 = int((y1 - (p.bounds[1] + shift[1])) / res)
        img[:, max(r0, 0):r1, max(c0, 0):c1] = 210
        polys.append(p)
    path = tmp_path / "scene.tif"
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=3, dtype="uint8",
                       crs="EPSG:32617", transform=from_origin(x0, y1, res, res)) as dst:
        dst.write(img)
    return str(path), polys


def test_consensus_recovers_systematic_shift(tmp_path):
    path, polys = _scene(tmp_path)
    o = align.consensus(path, polys, R=8.0)
    assert abs(o.dx - 3.0) <= 0.35 and abs(o.dy + 2.1) <= 0.35, o


def test_refine_stays_near_consensus(tmp_path):
    path, polys = _scene(tmp_path, shift=(1.2, 0.9))
    o = align.consensus(path, polys, R=6.0)
    out = align.refine(path, polys[:10], o, R=2.0)
    for dx, dy, _gain, _weak in out:
        assert abs(dx - 1.2) <= 0.5 and abs(dy - 0.9) <= 0.5
