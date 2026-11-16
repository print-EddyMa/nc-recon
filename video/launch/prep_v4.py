"""Scene data for the v4 launch film: `python3 video/launch/prep_v4.py`.

assets/v4/buildings.json: Swannanoa's 823 outlines as [u, v, long_m, short_m, angle_deg]
in the site's terrain UV frame, with NO damage level: the film shows every building
being read, and damage only as the 70 m smoothed density the public site already shows.
"""
import json, math, os
from pyproj import Transformer
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
L = json.load(open(os.path.join(ROOT, "site/assets/terrain/layers.json")))
X0, Y0, X1, Y1 = L["bbox_utm"]
utm = Transformer.from_crs(4326, 32617, always_xy=True).transform
fc = json.load(open(os.path.join(ROOT, "pipeline/data/output/ops/swannanoa.geojson")))
out = []
for f in fc["features"]:
    if f["geometry"]["type"] != "Polygon":
        continue
    ring = [utm(*c) for c in f["geometry"]["coordinates"][0]]
    from shapely.geometry import Polygon
    r = Polygon(ring).minimum_rotated_rectangle
    xs, ys = r.exterior.coords.xy
    e = sorted([(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]), math.degrees(math.atan2(ys[i + 1] - ys[i], xs[i + 1] - xs[i]))) for i in range(2)])
    c = r.centroid
    out.append([round((c.x - X0) / (X1 - X0), 5), round((Y1 - c.y) / (Y1 - Y0), 5), round(e[1][0], 1), round(e[0][0], 1), round(e[1][1], 1)])
os.makedirs(os.path.join(HERE, "assets", "v4"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "assets", "v4", "buildings.json"), "w"), separators=(",", ":"))
cu = sum(b[0] for b in out) / len(out); cv = sum(b[1] for b in out) / len(out)
print(len(out), "buildings; centre uv", round(cu, 3), round(cv, 3))
