import csv
import json
import os

import pytest

from terratriage.ops.disseminate import exports

AREA = "chimney_rock"
HAVE = os.path.exists(os.path.join(exports.OPS_OUT, f"{AREA}.geojson"))


@pytest.mark.skipif(not HAVE, reason="no ops output for chimney_rock")
def test_exports_round_trip(tmp_path):
    import pyogrio
    paths = exports.export_area(AREA, out_dir=str(tmp_path))
    n = len(json.load(open(paths["geojson"]))["features"])
    tot = 0
    for fmt in ("gpkg", "filegdb"):
        layers = [l[0] for l in pyogrio.list_layers(paths[fmt])]
        assert "structures" in layers
        tot = sum(pyogrio.read_info(paths[fmt], layer=l)["features"] for l in layers)
        assert tot == n
    rows = list(csv.DictReader(open(paths["csv"])))
    assert len(rows) == n and all(r["usng_10m"].startswith("17S") for r in rows)
    assessed = [r for r in rows if r["DMG_LEVEL"] != "Not Assessed"]
    assert assessed and all(r["ASMT_TYPE"] == "Remote Sensing" for r in assessed)
    assert all(r["ASMT_TYPE"] == "Unknown" for r in rows if r["DMG_LEVEL"] == "Not Assessed")
    assert all(r["DIS_NUMBER"] == "DR-4827-NC" for r in rows)
    assert "Not an official" in rows[0]["disclaimer"]
    gj = json.load(open(paths["geojson"]))
    assert "crs" not in gj                                   # RFC 7946
    for f in gj["features"]:
        if f["geometry"]["type"] == "Polygon":
            ring = f["geometry"]["coordinates"][0]
            area2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))
            assert area2 > 0                                 # exterior ring CCW


def test_public_mode_refuses_building_level():
    with pytest.raises(PermissionError):
        exports.export_area(AREA, mode="public")
