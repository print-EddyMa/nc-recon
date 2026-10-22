"""Cross-module integration checks added while merging the parallel work of
2026-10-22 (any-hazard engine, response products, photos, lidar, UI)."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(__file__)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server
    import terratriage.ops.api as api

    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    return TestClient(server.app), tmp_path


def test_sidecar_geojson_is_never_listed_as_an_area(client):
    c, out = client
    fc = {"type": "FeatureCollection", "features": [], "properties": {"aoi": {"id": "zz_area", "role": "TUNE"}}}
    (out / "zz_area.geojson").write_text(json.dumps(fc))
    (out / "zz_area.response.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    (out / "zz_area.public.geojson").write_text("{}")
    r = c.get("/ops/areas")
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == ["zz_area"]


def test_ncr_ops_out_moves_every_writer(tmp_path):
    """A scratch run must never write into the outputs a live server serves:
    every module that reads or writes assessments takes NCR_OPS_OUT."""
    import subprocess

    code = (
        "import importlib, json, os\n"
        "mods = ['api', 'pipeline', 'truth', 'analyze.evaluate', 'analyze.fema_reference',\n"
        "        'analyze.field_reference', 'analyze.ground_change', 'analyze.impact',\n"
        "        'analyze.sarcop_reference', 'disseminate.aggregate', 'disseminate.brief',\n"
        "        'disseminate.exports', 'response']\n"
        "out = {}\n"
        "for m in mods:\n"
        "    mod = importlib.import_module('terratriage.ops.' + m)\n"
        "    out[m] = getattr(mod, 'OPS_OUT', None) or getattr(mod, 'OUT', None) or mod.ops_out()\n"
        "print(json.dumps(out))\n"
    )
    env = dict(os.environ, NCR_OPS_OUT=str(tmp_path), PYTHONPATH=os.path.join(HERE, "..", "src"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    paths = json.loads(r.stdout.strip().splitlines()[-1])
    assert all(p == str(tmp_path) for p in paths.values()), paths
    src = os.path.join(HERE, "..", "src", "terratriage", "ops")
    for dp, _, fs in os.walk(src):
        for f in fs:
            if f.endswith(".py") and not (dp == src and f == "__init__.py"):
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    assert '"output", "ops"' not in fh.read(), f"{f} builds its own output path"


def test_routers_do_not_collide():
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server

    seen = {}
    for r in server.app.routes:
        for m in sorted(getattr(r, "methods", None) or []):
            key = (m, getattr(r, "path", ""))
            assert key not in seen, f"duplicate route {key}"
            seen[key] = r
