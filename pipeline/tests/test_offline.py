"""Offline packs: build, verify, import, and serve an area with the network cut.

The end-to-end test runs in a fresh Python process with every data path
relocated to scratch and a socket-level kill switch that refuses (and
records) any connection that is not loopback. It passes only if the app
serves the area, its imagery, a basemap, the exports, a label and a Verify
task without a single outbound attempt.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest

HERE = os.path.dirname(__file__)
PIPELINE = os.path.abspath(os.path.join(HERE, ".."))
SRC_FC = os.path.join(PIPELINE, "data", "output", "ops", "old_fort.geojson")
AREA = "town_ab12"
EVENT = "storm-offline-2026"


def _jpeg() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (200, 198, 190)).save(buf, "JPEG")
    return buf.getvalue()


def _listing(root: str) -> dict[str, str]:
    out = {}
    for dirpath, _d, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A source machine with one assessed operational area, and an empty
    destination machine, both in scratch."""
    if not os.path.exists(SRC_FC):
        pytest.skip("no stored assessment to build the fixture from")
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from terratriage.ops.collect import base
    from terratriage.ops.geodesy import transformer
    from terratriage.ops.offline import basemap, pack
    from terratriage.ops.plan import events as ev

    src, dst = tmp_path / "src", tmp_path / "dst"
    for root in (src, dst):
        for sub in ("output", "raw", "basemap", "cache", "labels", "truth"):
            (root / sub).mkdir(parents=True)
    with open(SRC_FC, encoding="utf-8") as fh:
        fc = json.load(fh)
    # a few buildings close together, so the rasters stay small
    import math

    lon0, lat0 = fc["features"][0]["properties"]["centroid"]
    near = [f for f in fc["features"] if math.hypot((f["properties"]["centroid"][0] - lon0) * 90000,
                                                    (f["properties"]["centroid"][1] - lat0) * 111000) < 80]
    fc["features"] = near[:4]
    fc["properties"]["aoi"] = {"id": AREA, "role": "OPS", "name": "Test town", "county": "McDowell",
                               "center": fc["features"][0]["properties"]["centroid"]}
    (src / "output" / f"{AREA}.geojson").write_text(json.dumps(fc))
    (src / "output" / f"{AREA}.responder.json").write_text(json.dumps({"structures": {"x": {"address": "1 Main St"}}}))
    (src / "output" / f"{AREA}.impact.json").write_text(json.dumps({"tracts": []}))
    # small before / after rasters on the structures (UTM 17N, 0.3 m)
    lons = [f["properties"]["centroid"][0] for f in fc["features"]]
    lats = [f["properties"]["centroid"][1] for f in fc["features"]]
    to = transformer("storage", 6346).transform
    x0, y0 = to(min(lons), min(lats))
    x1, y1 = to(max(lons), max(lats))
    x0, y0, x1, y1 = x0 - 30, y0 - 30, x1 + 30, y1 + 30
    w, h = int((x1 - x0) / 0.3), int((y1 - y0) / 0.3)
    rdir = src / "raw" / AREA
    rdir.mkdir()
    grad = (np.add.outer(np.arange(h), np.arange(w)) % 140 + 60).astype("uint8")   # smooth: compresses fast
    side = {"area": AREA}
    for role, name in (("pre", "pre_2023-02-18.tif"), ("post", "post_2026-10-05.tif")):
        p = rdir / name
        with rasterio.open(p, "w", driver="GTiff", width=w, height=h, count=3, dtype="uint8", crs="EPSG:6346",
                           transform=from_origin(x0, y1, 0.3, 0.3), tiled=True, compress="DEFLATE") as d:
            d.write(np.stack([grad, grad, grad]))
        side[role] = {"source": "nc_2020_2023" if role == "pre" else "eri", "path": str(p),
                      "date_min": name[len(role) + 1:len(role) + 11], "date_max": name[len(role) + 1:len(role) + 11],
                      "date_label": role, "provenance": {"source": "test", "source_url": "", "license": "test"}}
    (rdir / "imagery.json").write_text(json.dumps(side))

    reg = tmp_path / "src_registry.yaml"
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(reg))
    ev.add_provisional_event(EVENT, "Storm offline", "2026-10-01", post_days=(0, 120))
    ev.add_ops_area(AREA, EVENT, "Test town", lons[0], lats[0], county="McDowell")

    for mod in (pack,):
        monkeypatch.setattr(mod, "OPS_OUT", str(src / "output"))
        monkeypatch.setattr(mod, "RAW_DIR", str(src / "raw"))
        monkeypatch.setattr(mod, "BASEMAP_DIR", str(src / "basemap"))
        monkeypatch.setattr(mod, "OPS_CACHE", str(src / "cache"))
    monkeypatch.setattr(base, "OPS_CACHE", str(src / "cache"))
    monkeypatch.setattr(basemap, "CONTEXT_ZOOMS", (11, 12))
    monkeypatch.setattr(basemap, "DETAIL_ZOOMS", (14, 15))
    return {"src": src, "dst": dst, "tmp": tmp_path, "fake_fetch": lambda url: _jpeg()}


def _build(world, **kw):
    from terratriage.ops.offline import pack

    return pack.build(AREA, str(world["tmp"] / "packs"), fetch=world["fake_fetch"], **kw)


def _to_dst(world, monkeypatch):
    from terratriage.ops.collect import base
    from terratriage.ops.offline import pack

    d = world["dst"]
    monkeypatch.setattr(pack, "OPS_OUT", str(d / "output"))
    monkeypatch.setattr(pack, "RAW_DIR", str(d / "raw"))
    monkeypatch.setattr(pack, "BASEMAP_DIR", str(d / "basemap"))
    monkeypatch.setattr(pack, "OPS_CACHE", str(d / "cache"))
    monkeypatch.setattr(base, "OPS_CACHE", str(d / "cache"))
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(world["tmp"] / "dst_registry.yaml"))


# --------------------------------------------------------------------------- #
def test_pack_holds_no_addresses_and_marks_display_copies(world):
    root, m = _build(world)
    paths = {f["path"] for f in m["files"]}
    assert f"outputs/{AREA}.geojson" in paths and f"outputs/{AREA}.impact.json" in paths
    assert not any("responder" in p for p in paths)
    assert not os.path.exists(os.path.join(root, "outputs", f"{AREA}.responder.json"))
    assert any("addresses" in x for x in m["left_out"])
    rasters = [f for f in m["files"] if f["kind"] == "raster"]
    assert len(rasters) == 2 and all(f["display_copy"] for f in rasters)
    assert m["basemap"]["tiles"] > 0 and m["basemap"]["license"].startswith("US Government")
    assert "no sync" in m["labels"]
    side = json.load(open(os.path.join(root, "raw", AREA, "imagery.json")))
    assert "/" not in side["post"]["path"]                     # no paths from the building machine


def test_building_never_writes_to_the_live_outputs(world):
    before = (_listing(str(world["src"] / "output")), _listing(str(world["src"] / "raw")))
    _build(world)
    assert (_listing(str(world["src"] / "output")), _listing(str(world["src"] / "raw"))) == before


def test_tampered_or_padded_packs_are_refused(world):
    from terratriage.ops.offline import pack

    root, m = _build(world)
    pack.verify(root)
    victim = os.path.join(root, "outputs", f"{AREA}.geojson")
    with open(victim, "ab") as fh:
        fh.write(b" ")
    with pytest.raises(pack.PackError, match="checksum"):
        pack.verify(root)
    root2, _ = _build(world)
    with open(os.path.join(root2, "outputs", "extra.json"), "w") as fh:
        fh.write("{}")
    with pytest.raises(pack.PackError, match="not in the manifest"):
        pack.verify(root2)


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink", "two_roots"])
def test_unsafe_tars_are_refused(tmp_path, kind):
    from terratriage.ops.offline import pack

    t = tmp_path / f"{kind}.tar"
    with tarfile.open(t, "w") as tf:
        def add(name, data=b"x", **attrs):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            for k, v in attrs.items():
                setattr(ti, k, v)
            tf.addfile(ti, io.BytesIO(data))
        if kind == "traversal":
            add("groma-pack-x/../../evil.txt")
        elif kind == "absolute":
            add("/tmp/evil.txt")
        elif kind == "symlink":
            ti = tarfile.TarInfo("groma-pack-x/link")
            ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tf.addfile(ti)
        else:
            add("a/manifest.json")
            add("b/manifest.json")
    with pytest.raises(pack.PackError):
        pack.import_pack(str(t))
    assert not (tmp_path.parent / "evil.txt").exists()


def test_test_areas_and_oversize_packs_are_refused(world, monkeypatch):
    from terratriage.ops.offline import pack

    monkeypatch.setattr(pack, "_specs", lambda a: (EVENT, {}, {"role": "TEST"}, "config"))
    with pytest.raises(pack.PackError, match="hold-out"):
        _build(world)
    monkeypatch.undo()


def test_size_cap(world):
    from terratriage.ops.offline import pack

    with pytest.raises(pack.PackError, match="cap"):
        _build(world, max_mb=0.001)


def test_import_registers_the_area_keeps_labels_and_refuses_conflicts(world, monkeypatch):
    from terratriage.ops.offline import pack
    from terratriage.ops.plan import events as ev

    tar_path, _m = _build(world, as_tar=True)
    _to_dst(world, monkeypatch)
    labels = world["dst"] / "labels" / f"{AREA}.csv"
    labels.write_text("ncr_id,label\nx,minor\n")
    r = pack.import_pack(tar_path)
    assert r["area"] == AREA and r["written"] > 0
    assert f"event {EVENT}" in r["registered"] and f"area {AREA}" in r["registered"]
    assert AREA in ev.load_events()[EVENT].aois
    assert labels.read_text() == "ncr_id,label\nx,minor\n"
    assert not (world["dst"] / "output" / f"{AREA}.responder.json").exists()
    side = json.load(open(world["dst"] / "raw" / AREA / "imagery.json"))
    assert side["post"]["path"].startswith(str(world["dst"] / "raw")) and side["post"]["display_copy"]
    assert pack.import_pack(tar_path)["written"] == 0                     # idempotent
    (world["dst"] / "output" / f"{AREA}.geojson").write_text("{}")         # a different copy here
    with pytest.raises(pack.PackError, match="--replace"):
        pack.import_pack(tar_path)
    assert pack.import_pack(tar_path, replace=True)["written"] >= 1


def test_network_gate_and_offline_csp(monkeypatch):
    from terratriage.ops import guard

    monkeypatch.setenv("NCR_OFFLINE", "1")
    assert guard.needs_network("POST", "/ops/assess") and guard.needs_network("GET", "/ops/coverage")
    assert guard.needs_network("POST", "/ops/areas/x/response") and guard.needs_network("GET", "/feed/fiman")
    assert not guard.needs_network("GET", "/ops/areas/x/response")
    assert not guard.needs_network("POST", "/ops/labels")
    csp = guard.csp(None)
    assert "connect-src 'self' blob: data:;" in csp and "img-src 'self' data: blob:;" in csp
    assert "https:" not in csp and "cartocdn" not in csp
    monkeypatch.delenv("NCR_OFFLINE")
    assert not guard.needs_network("POST", "/ops/assess")


# --------------------------------------------------------------------------- #
# the proof: a fresh process, everything relocated, the network cut
# --------------------------------------------------------------------------- #
OFFLINE_SCRIPT = r'''
import json, os, socket, sys, zipfile, io
attempts = []
_LOOP = ("127.0.0.1", "::1", "localhost")
def _deny(addr):
    host = addr[0] if isinstance(addr, tuple) else addr
    return isinstance(host, str) and host not in _LOOP
_real_connect = socket.socket.connect
def connect(self, addr):
    if self.family in (socket.AF_INET, socket.AF_INET6) and _deny(addr):
        attempts.append(str(addr)); raise OSError("network is off (test kill switch)")
    return _real_connect(self, addr)
socket.socket.connect = connect
socket.socket.connect_ex = lambda self, addr: connect(self, addr) or 0
_real_gai = socket.getaddrinfo
def gai(host, *a, **k):
    if host not in _LOOP and host is not None:
        attempts.append(f"dns:{host}"); raise socket.gaierror("network is off (test kill switch)")
    return _real_gai(host, *a, **k)
socket.getaddrinfo = gai

sys.path.insert(0, os.path.join(sys.argv[1], "src")); sys.path.insert(0, sys.argv[1])
area = sys.argv[2]
from fastapi.testclient import TestClient
import server
from terratriage.ops.offline import api as offline_api
if not any(getattr(r, "path", "") == "/ops/offline" for r in server.app.routes):
    server.app.include_router(offline_api.router)     # until server.py includes it
c = TestClient(server.app)
out = {}
def get(path, **kw):
    r = c.get(path, **kw); out[path] = r.status_code; return r
st = get("/ops/offline").json()
out["offline_flag"] = st["offline"]; out["basemap"] = st["basemap"]["available"]
style = get("/ops/basemap/style.json").json()
tile = style["sources"]["usgs-topo"]["tiles"][0]
out["style_local"] = tile.startswith("http://testserver/ops/basemap/")
z = style["sources"]["usgs-topo"]["maxzoom"]
from terratriage.ops.offline.basemap import lonlat_to_tile
fc = get(f"/ops/areas/{area}").json()
lon, lat = fc["features"][0]["properties"]["centroid"]
x, y = lonlat_to_tile(lon, lat, z)
r = get(f"/ops/basemap/{z}/{x}/{y}.jpg"); out["basemap_tile_type"] = r.headers.get("content-type")
out["basemap_missing"] = c.get("/ops/basemap/3/0/0.jpg").status_code
out["areas_has"] = area in [a["id"] for a in get("/ops/areas").json()]
nid = fc["features"][0]["properties"]["ncr_id"]
r = get(f"/ops/areas/{area}/chip/{nid}/post.png"); out["chip_type"] = r.headers.get("content-type")
x17, y17 = lonlat_to_tile(lon, lat, 17)
r = get(f"/ops/areas/{area}/tiles/post/17/{x17}/{y17}"); out["tile_bytes"] = len(r.content)
r = get(f"/ops/areas/{area}/export.zip")
names = zipfile.ZipFile(io.BytesIO(r.content)).namelist() if r.status_code == 200 else []
out["export_names"] = names
get(f"/ops/areas/{area}/brief.html")
r = c.post("/ops/labels", json={"area": area, "ncr_id": nid, "label": "minor", "labeler": "offline"})
out["label"] = r.status_code
get(f"/ops/truth/next?area={area}&worker=offline")
out["csp"] = c.get("/health").headers.get("content-security-policy")
out["attempts"] = attempts
print("RESULT " + json.dumps(out))
'''


def test_area_is_fully_usable_with_the_network_cut(world, monkeypatch):
    tar_path, _m = _build(world, as_tar=True)
    _to_dst(world, monkeypatch)
    from terratriage.ops.offline import pack

    pack.import_pack(tar_path)
    d = world["dst"]
    env = {**os.environ, "NCR_OFFLINE": "1", "NCR_DEV_OPEN": "1",
           "NCR_OPS_OUT": str(d / "output"), "NCR_RAW_DIR": str(d / "raw"), "NCR_BASEMAP_DIR": str(d / "basemap"),
           "NCR_OPS_CACHE": str(d / "cache"), "NCR_OPS_REGISTRY": str(world["tmp"] / "dst_registry.yaml"),
           "NCR_LABELS_DIR": str(d / "labels"), "NCR_TRUTH_DIR": str(d / "truth"),
           "NCR_JOBS_FILE": str(world["tmp"] / "jobs.json"), "NCR_AUDIT_LOG": str(world["tmp"] / "audit.log")}
    script = world["tmp"] / "offline_check.py"
    script.write_text(OFFLINE_SCRIPT)
    p = subprocess.run([sys.executable, str(script), PIPELINE, AREA], env=env, capture_output=True, text=True,
                       timeout=600)
    line = next((x for x in p.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line, p.stdout[-2000:] + p.stderr[-4000:]
    r = json.loads(line[len("RESULT "):])
    assert r["attempts"] == [], f"outbound network attempts while offline: {r['attempts']}"
    assert r["offline_flag"] and r["basemap"] and r["style_local"]
    assert r["basemap_tile_type"] == "image/jpeg" and r["basemap_missing"] == 204
    assert r["areas_has"] and r[f"/ops/areas/{AREA}"] == 200
    assert r["chip_type"] == "image/png" and r["tile_bytes"] > 100
    assert any(n.endswith(".gpkg") for n in r["export_names"]), r["export_names"]
    assert any(n.endswith(".kml") for n in r["export_names"]) and any(n.endswith(".csv") for n in r["export_names"])
    assert r[f"/ops/areas/{AREA}/brief.html"] == 200 and r["label"] == 200
    assert r[f"/ops/truth/next?area={AREA}&worker=offline"] == 200
    assert "connect-src 'self' blob: data:;" in r["csp"]
    assert (d / "labels" / f"{AREA}.csv").exists()
