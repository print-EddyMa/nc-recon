"""Generate real building crops (pre/post) + analysis arrays for the showcase artifact."""
import json, math, base64, io, os
from PIL import Image

ROOT = os.path.expanduser("~/terratriage")
TILES = os.path.join(ROOT, "web/public/tiles/old_fort")
GJ = json.load(open(os.path.join(ROOT, "pipeline/data/output/old_fort.geojson")))
F = GJ["features"]
Z = 17
N = 2 ** Z

def lonlat_to_px(lon, lat):
    x = (lon + 180.0) / 360.0 * N
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * N
    return x, y  # in tile units; *256 for pixels

def load_tile(kind, tx, ty):
    p = os.path.join(TILES, kind, str(Z), str(tx), f"{ty}.jpg")
    if os.path.exists(p):
        return Image.open(p).convert("RGB")
    return Image.new("RGB", (256, 256), (52, 54, 60))

def crop(kind, lon, lat, box=116, out=220):
    xu, yu = lonlat_to_px(lon, lat)
    tx0, ty0 = int(xu), int(yu)
    # stitch 3x3 around the center tile
    canvas = Image.new("RGB", (768, 768))
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            canvas.paste(load_tile(kind, tx0 + dx, ty0 + dy), ((dx + 1) * 256, (dy + 1) * 256))
    cx = (xu - tx0) * 256 + 256
    cy = (yu - ty0) * 256 + 256
    half = box / 2
    im = canvas.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((out, out), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=74)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

# ---- pick example buildings ----
IDS = {
    # id : (lon, lat)  -- from the geojson
}
def find(bid):
    for f in F:
        if f["properties"]["id"] == bid:
            c = f["properties"]["centroid"]
            return c[0], c[1]
    raise KeyError(bid)

EXAMPLES = {
    "none":      "old_fort-000009",   # cnn0 cd0 -> class 0
    "minor":     "old_fort-000038",   # cnn1 cd1 -> class 1
    "major":     "old_fort-000461",   # cnn2 cd2 -> class 2
    "destroyed": "old_fort-000205",   # cnn3 cd3 -> class 3
    "disagree":  "old_fort-000136",   # cnn3 cd0 -> routed to review
}
crops = {}
for k, bid in EXAMPLES.items():
    lon, lat = find(bid)
    crops[k] = {"id": bid, "pre": crop("pre", lon, lat), "post": crop("post", lon, lat)}

# ---- analysis arrays ----
def sc(f, k): return (f["properties"].get("sources") or {}).get(k)
lons = [f["properties"]["centroid"][0] for f in F]
lats = [f["properties"]["centroid"][1] for f in F]
lo0, lo1, la0, la1 = min(lons), max(lons), min(lats), max(lats)
scatter = []
for f in F:
    c = f["properties"]["centroid"]
    nx = (c[0] - lo0) / (lo1 - lo0)
    ny = 1 - (c[1] - la0) / (la1 - la0)   # flip for screen y
    scatter.append([round(nx, 4), round(ny, 4), f["properties"]["damage_class"]])

# area distribution by class (log-ish buckets in m2)
buckets = [0, 50, 100, 150, 250, 400, 10000]
labels = ["<50", "50-100", "100-150", "150-250", "250-400", "400+"]
area_by_class = [[0] * len(labels) for _ in range(4)]
for f in F:
    a = f["properties"].get("area_m2", 0)
    cl = f["properties"]["damage_class"]
    for i in range(len(labels)):
        if buckets[i] <= a < buckets[i + 1]:
            area_by_class[cl][i] += 1
            break

# median area by class
from statistics import median
med_area = []
for cl in range(4):
    xs = [f["properties"]["area_m2"] for f in F if f["properties"]["damage_class"] == cl]
    med_area.append(round(median(xs)) if xs else 0)

out = {
    "crops": crops,
    "scatter": scatter,
    "areaLabels": labels,
    "areaByClass": area_by_class,
    "medArea": med_area,
    "bbox": [round(lo0, 5), round(la0, 5), round(lo1, 5), round(la1, 5)],
}
open(os.path.join(os.path.dirname(__file__), "assets.json"), "w").write(json.dumps(out))
print("crops:", {k: (len(v["pre"]), len(v["post"])) for k, v in crops.items()})
print("scatter pts:", len(scatter), " area buckets:", labels)
print("median m2 by class 0..3:", med_area)
print("area_by_class:", area_by_class)
print("total base64 KB:", round(sum(len(v["pre"]) + len(v["post"]) for v in crops.values()) / 1024))
