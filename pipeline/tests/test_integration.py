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


def test_routers_do_not_collide():
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server

    seen = {}
    for r in server.app.routes:
        for m in sorted(getattr(r, "methods", None) or []):
            key = (m, getattr(r, "path", ""))
            assert key not in seen, f"duplicate route {key}"
            seen[key] = r
