"""E5 water-surface sources from NCEM's published Helene peak stages
(collect/ncem_peak_stage), against dated fixtures, and their use by
analyze.flood."""
import json
import os

import pytest

from terratriage.ops.analyze import flood
from terratriage.ops.collect import ncem_peak_stage as nps
from terratriage.ops.collect.base import SourceUnavailable
from terratriage.ops.heights import Depth, Elevation

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
WNC = (-82.9, 35.45, -82.0, 35.75)   # Canton to Old Fort, Marshall to Asheville


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def served(monkeypatch, tmp_path):
    monkeypatch.setattr(nps, "DiskCache", lambda ns: _NoCache())

    def fake(url, params=None, **kw):
        if "Peak_Stage_Helene" in url:
            return _load("ncem_peak_stage_helene_2026-10-07.geojson")
        if url == nps.FIMAN_URL:
            return _load("fiman_datums_wnc_2026-10-07.json")
        raise AssertionError(url)

    monkeypatch.setattr(nps, "http_json", fake)


class _NoCache:
    def get(self, key, max_age_s=None):
        return None

    def put(self, key, value):
        pass


def test_layer_registry():
    assert nps.layer_for("helene-2024-nc") and nps.layer_for("DR-4827-NC")
    assert nps.layer_for("florence-2018-nc") is None


def test_sources_skip_truncated_and_verify_datums(served):
    sources, warnings, prov = nps.wse_sources("helene-2024-nc", WNC, "2024-09-25", "2025-06-02")
    refs = {s.ref: s for s in sources}
    # a USGS gauge whose datum matches FIMAN's NAVD88 record: verified, tight sigma
    pigeon = refs["NCEM peak stage: Pigeon River near Canton (USGS)"]
    assert pigeon.sigma_m == nps.SIGMA_VERIFIED_M
    assert abs(pigeon.wse.m - 2607.37 * 0.3048) < 1e-6 and pigeon.wse.datum == "NAVD88"
    assert pigeon.max_dist_m == nps.MAX_DIST_M and pigeon.kind == "gauge_crest"
    # an NCEM gauge with no datum record: kept, wide sigma, warned
    marion = refs["NCEM peak stage: CATAWBA RIVER at US221, Marion (NCEM)"]
    assert marion.sigma_m == nps.SIGMA_UNVERIFIED_M
    assert any("Marion" in w and "datum not verifiable" in w for w in warnings)
    # gauges that stopped reporting are lower bounds and are left out, with a warning
    assert not any("Old Fort" in r for r in refs)
    assert any("Old Fort" in w and "stopped reporting" in w for w in warnings)
    assert not any("Biltmore" in r for r in refs)
    # provenance rows mirror the sources
    assert len(prov) == len(sources) and {p["datum_status"] for p in prov} <= {"navd88_verified", "ngvd29_converted", "unverified"}
    assert sum(p["datum_status"] == "navd88_verified" for p in prov) >= 3


def test_incident_window_filters_peak_time(served):
    sources, warnings, _ = nps.wse_sources("helene-2024-nc", WNC, "2024-10-15", "2025-06-02")
    assert sources == [] and all("outside the incident window" in w for w in warnings if "peak time" in w)


def test_unknown_event_has_no_source(served):
    sources, warnings, prov = nps.wse_sources("florence-2018-nc", WNC)
    assert sources == [] and prov == [] and "no NCEM peak-stage layer" in warnings[0]


def test_upstream_failure_never_raises(monkeypatch):
    monkeypatch.setattr(nps, "DiskCache", lambda ns: _NoCache())

    def boom(*a, **k):
        raise SourceUnavailable("503 from spartagis")

    monkeypatch.setattr(nps, "http_json", boom)
    sources, warnings, prov = nps.wse_sources("helene-2024-nc", WNC, "2024-09-25")
    assert sources == [] and prov == [] and "E5 unavailable" in warnings[0]


def test_crest_feeds_the_flood_channel(served):
    sources, _, _ = nps.wse_sources("helene-2024-nc", WNC, "2024-09-25", "2025-06-02")
    pigeon = next(s for s in sources if "Pigeon River near Canton" in s.ref)
    # a structure 400 m from the gauge is on its reach; 5 km away is not
    near = flood.pick_source(pigeon.lon + 0.004, pigeon.lat, sources)
    assert near and near[0].ref == pigeon.ref and near[1] > pigeon.sigma_m
    assert flood.pick_source(pigeon.lon + 0.05, pigeon.lat, sources) is None
    # ground 3 m below the crest, slab foundation: water is well above the outlets
    probs, depth = flood.class_probs(pigeon.wse, near[1], Elevation.of(pigeon.wse.m - 3.0), 0.5,
                                     Depth.of(0.5, "ft"), 0.3, False, n=500)
    assert depth["d_ff_m_median"] > 2.0 and probs.argmax() >= 3
    # ground 5 m above the crest: no water reaches it
    probs2, _ = flood.class_probs(pigeon.wse, near[1], Elevation.of(pigeon.wse.m + 5.0), 0.5,
                                  Depth.of(0.5, "ft"), 0.3, False, n=500)
    assert probs2[0] > 0.99


def test_name_normalisation_matches_fiman_spellings():
    assert nps._norm("CATAWBA RIVER @ US221, Marion") == nps._norm("Catawba River at US221 Marion")
