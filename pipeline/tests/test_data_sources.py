import os
import subprocess

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_no_legacy_usgs_waterservices_calls():
    """Legacy NWIS WaterServices is decommissioned Q1 2027 (503s since Aug 2026)."""
    out = subprocess.run(
        ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.tsx",
         "--include=*.mjs", "--exclude-dir=node_modules", "--exclude-dir=.venv",
         "https://waterservices.usgs.gov",
         os.path.join(REPO, "pipeline", "src"), os.path.join(REPO, "pipeline", "server.py"),
         os.path.join(REPO, "pipeline", "scripts"), os.path.join(REPO, "web", "src"),
         os.path.join(REPO, "web", "scripts")],
        capture_output=True, text=True,
    )
    hits = [ln for ln in out.stdout.splitlines() if "# legacy-probe" not in ln]
    assert not hits, "legacy USGS calls remain:\n" + "\n".join(hits)


def test_usgs_fixture_schema(fixture_json):
    fc = fixture_json("usgs_latest_continuous_00065_2026-09-26.json")
    p = fc["features"][0]["properties"]
    for k in ("monitoring_location_id", "time", "value", "unit_of_measure", "parameter_code"):
        assert k in p


@pytest.mark.live
def test_usgs_water_live():
    from terratriage.ops.collect.usgs_water import USGSWater
    layer = USGSWater().fetch()
    assert len(layer.data["features"]) > 150
    assert layer.provenance.source_url.startswith("https://api.waterdata.usgs.gov")


@pytest.mark.live
def test_nc_orthos_coverage_live():
    from terratriage.ops.collect import nc_orthos
    assert nc_orthos.covered("nc_helene_2025", -82.009, 35.684)      # Marion, McDowell Co.
    assert not nc_orthos.covered("nc_helene_2025", -78.64, 35.78)    # Raleigh, outside the 13 counties
