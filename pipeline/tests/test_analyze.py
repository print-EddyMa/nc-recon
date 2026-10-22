import numpy as np
import pytest
from shapely.geometry import Point, box

from terratriage.ops.analyze import calibration, flood, metrics
from terratriage.ops.analyze.classes import FEMA, K, nc_field_to_fema, xbd_to_fema_matrix
from terratriage.ops.analyze.fusion import Channel, decide, pool
from terratriage.ops.heights import Depth, Elevation


# ------------------------------ metrics ---------------------------------- #
def test_metrics_match_sklearn():
    from sklearn.metrics import cohen_kappa_score, f1_score
    rng = np.random.default_rng(1)
    y = rng.integers(0, 5, 400)
    p = np.clip(y + rng.integers(-1, 2, 400), 0, 4)
    cm = metrics.confusion(y, p, 5)
    assert metrics.macro_f1(cm) == pytest.approx(f1_score(y, p, average="macro"), abs=1e-9)
    assert metrics.quadratic_weighted_kappa(y, p, 5) == pytest.approx(
        cohen_kappa_score(y, p, weights="quadratic"), abs=1e-9)


def test_metric_absent_class_is_none_not_zero():
    assert metrics.recall_of([0, 0, 1], [0, 1, 1], cls=4) is None


def test_ece_perfect_calibration_small():
    rng = np.random.default_rng(0)
    n = 20000
    conf = rng.uniform(0.3, 1.0, n)
    y = (rng.random(n) < conf).astype(int)          # class 1 correct w.p. conf
    probs = np.stack([1 - conf, conf], axis=1)
    pred_ok = np.where(conf >= 0.5, y, 1 - y)
    e, _ = metrics.ece(probs, np.where(conf >= 0.5, y, 1 - y) * 0 + y)
    assert e < 0.03
    _ = pred_ok


def test_cluster_bootstrap_wider_than_iid():
    rng = np.random.default_rng(0)
    clusters = np.repeat(np.arange(20), 50)
    effect = rng.normal(0, 1, 20)[clusters]          # strong within-cluster correlation
    x = effect + rng.normal(0, 0.1, len(clusters))
    lo, hi = metrics.cluster_bootstrap(lambda i: float(x[i].mean()), clusters, n_boot=300)
    iid_lo, iid_hi = metrics.cluster_bootstrap(lambda i: float(x[i].mean()),
                                               np.arange(len(x)), n_boot=300)
    assert (hi - lo) > 3 * (iid_hi - iid_lo)


# --------------------------- calibration --------------------------------- #
def test_temperature_recovers_overconfidence():
    rng = np.random.default_rng(0)
    n, k = 3000, 4
    true_logits = rng.normal(0, 1.5, (n, k))
    y = np.array([rng.choice(k, p=calibration.softmax(true_logits[i:i + 1])[0]) for i in range(n)])
    T = calibration.fit_temperature(true_logits * 5.0, y)
    assert 3.5 < T < 7.0


def test_temperature_refuses_test_labels():
    with pytest.raises(ValueError, match="TUNE"):
        calibration.fit_temperature(np.zeros((30, 4)), np.zeros(30, int), ["TUNE"] * 29 + ["TEST"])


def test_conformal_coverage_close_to_target():
    rng = np.random.default_rng(3)
    n, k = 4000, 5
    logits = rng.normal(0, 2, (n, k))
    probs = calibration.softmax(logits)
    y = np.array([rng.choice(k, p=p) for p in probs])
    q = calibration.conformal_quantile(calibration.aps_scores(probs[:2000], y[:2000]), 0.10)
    sets = calibration.aps_sets(probs[2000:], q)
    cov = np.mean([t in s for t, s in zip(y[2000:], sets)])
    assert 0.87 <= cov <= 0.95


# ------------------------------ crosswalks ------------------------------- #
def test_crosswalks_row_stochastic():
    assert np.allclose(xbd_to_fema_matrix().sum(axis=1), 1)
    assert nc_field_to_fema("moderate", "lower")[FEMA.index("minor")] == 1
    assert nc_field_to_fema("moderate", "upper")[FEMA.index("major")] == 1


# ------------------------------- fusion ---------------------------------- #
def test_pool_no_evidence_returns_prior():
    from terratriage.ops.analyze.classes import class_prior
    assert np.allclose(pool([]), class_prior())


def test_uninformative_channel_does_not_move_posterior():
    flat = Channel("E2", True, np.ones(K) / K, 1.0)
    assert np.allclose(pool([flat]), pool([]))


def test_strong_evidence_wins_and_is_explained():
    L = np.array([0.01, 0.01, 0.02, 0.06, 0.90])
    v = decide([Channel("E1", True, L, 1.0), Channel("E5", True, L, 1.0)], calibrated=True)
    assert FEMA[v.label] == "destroyed" and not v.needs_review
    u = decide([Channel("E1", True, L, 1.0), Channel("E5", True, L, 1.0)], calibrated=False)
    assert u.needs_review and "UNCALIBRATED_SEVERE_CALL_DESTROYED" in u.review_reasons
    assert any(r.startswith("E1_FOR_DESTROYED") for r in v.reasons)


def test_abstain_when_key_channel_missing():
    v = decide([Channel("E1", False, unavailable_reason="POSSIBLE_CLOUD")])
    assert v.needs_review and "KEY_CHANNEL_E1_UNAVAILABLE" in v.review_reasons
    assert "E1_UNAVAILABLE_POSSIBLE_CLOUD" in v.reasons


def test_abstain_on_nonadjacent_split():
    # with the prior (0.40 no_damage, 0.10 destroyed) this pools to ~50/48
    L = np.array([0.20, 0.01, 0.01, 0.02, 0.76])
    v = decide([Channel("E1", True, L, 1.0)])
    assert v.needs_review
    assert any(r.startswith("NONADJACENT") for r in v.review_reasons)


def test_label_only_minor_not_forced_to_review():
    """Regression: with the prior double-counted, every CNN 'minor' fell below tau."""
    from terratriage.ops.analyze import channels
    from terratriage.ops.analyze.evidence import BuildingEvidence
    ch = channels.e1(BuildingEvidence(0), np.array([0.0, 9.0, 0.0, 0.0]), None)
    p = pool([ch])
    assert p.argmax() in (FEMA.index("affected"), FEMA.index("minor"))


# ------------------------------- flood (E5) ------------------------------ #
P = flood.matrix()["params"]


@pytest.mark.parametrize("d_in,expect", [(-6, "affected"), (6, "minor"), (20, "major"),
                                          (60, "major"), (100, "destroyed")])
def test_conventional_boundaries(d_in, expect):
    c = flood.depth_class(d_in * 0.0254, True, False, P, outlet_in=16)
    assert FEMA[c] == expect


@pytest.mark.parametrize("d_in,expect", [(-18, "affected"), (-6, "minor"), (3, "major"),
                                          (100, "destroyed")])
def test_manufactured_boundaries(d_in, expect):
    c = flood.depth_class(d_in * 0.0254, True, True, P, outlet_in=16)
    assert FEMA[c] == expect


def test_dry_ground_is_no_damage():
    assert FEMA[flood.depth_class(-2.0, False, False, P, 16)] == "no_damage"


def test_flood_mc_probs_sum_and_shift():
    wse = Elevation.of(103.0)
    lo, _ = flood.class_probs(wse, 0.1, Elevation.of(102.5), 0.05, Depth.of(1.0, "ft"), 0.05, False)
    hi, d = flood.class_probs(wse, 0.1, Elevation.of(100.0), 0.05, Depth.of(1.0, "ft"), 0.05, False)
    assert lo.sum() == pytest.approx(1) and hi.sum() == pytest.approx(1)
    assert np.dot(hi, np.arange(K)) > np.dot(lo, np.arange(K))
    assert d["d_ff_m_median"] == pytest.approx(3.0 - 0.3048, abs=0.05)


def test_pick_source_respects_domain():
    s = flood.WSESource("gauge_crest", "G", -82.0, 35.7, Elevation.of(400), 0.1, max_dist_m=1000)
    assert flood.pick_source(-82.0, 35.705, [s]) is not None
    assert flood.pick_source(-82.18, 35.63, [s]) is None


# ---------------------------- conflation --------------------------------- #
def _nsi(x, y, fid, occ="RES1-1SNB"):
    return {"geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": {"fd_id": fid, "occtype": occ}}


def test_conflation_pip_near_and_single_claim():
    from terratriage.ops.process.structures import conflate, unmatched_nsi
    d = 0.0002  # ~20 m
    a = box(-82.1800, 35.6300, -82.1799, 35.6301)
    b = box(-82.1800 + d, 35.6300, -82.1799 + d, 35.6301)
    pts = [_nsi(-82.17995, 35.63005, 1),            # inside a
           _nsi(-82.17995, 35.63005, 2),            # also inside a -> cannot be claimed twice
           _nsi(-82.1799 + d + 0.00005, 35.63005, 3, "RES2")]  # ~4.5 m east of b
    st = conflate([a, b], "osm", ["way/1", "way/2"], pts)
    assert st[0].match_method == "pip" and st[0].nsi["fd_id"] in (1, 2)
    assert st[1].match_method == "near" and st[1].flags["manufactured_home"]
    assert st[0].flags["residential"]                 # suffix stripped
    assert len(unmatched_nsi(st, pts)) == 1


def test_ncr_id_stable():
    from terratriage.ops.process.structures import ncr_id
    assert ncr_id("osm", "way/123") == ncr_id("osm", "way/123")
    assert ncr_id("osm", "way/123") != ncr_id("usa_structures", "way/123")
    _ = Point


def test_e2_z_baseline_does_not_force_damage_share():
    """An AOI where nothing changed must not produce 'changed' evidence."""
    from terratriage.ops.analyze import channels
    from terratriage.ops.analyze.evidence import BuildingEvidence
    rng = np.random.default_rng(0)
    evs = []
    for i in range(200):
        e = BuildingEvidence(i)
        e.m.update(ssim_fp=0.9 + rng.normal(0, 0.01), edge_loss=0.02, cva_fp=0.03, cva_ring=0.03)
        evs.append(e)
    base = channels.e2_baseline(evs)
    zs = [channels.e2(e, 1.0, base).detail["z"] for e in evs]
    assert np.mean(np.abs(zs) < 2.0) > 0.9
    # a genuinely changed building stands out
    hit = BuildingEvidence(999)
    hit.m.update(ssim_fp=0.2, edge_loss=0.4, cva_fp=0.3, cva_ring=0.2)
    assert channels.e2(hit, 1.0, base).detail["z"] > 3.5


def test_multipart_footprints_get_distinct_stable_ids():
    """A MultiPolygon building is assessed part by part; each part needs its
    own ncr_id (labels, chips and exports are keyed by it). The largest part
    keeps the bare source id so single-part ids never change."""
    from shapely.geometry import MultiPolygon, box

    from terratriage.ops.pipeline import part_ids
    from terratriage.ops.process.structures import ncr_id

    small, big = box(0, 0, 1, 1), box(5, 5, 9, 9)
    assert part_ids("51272758", big) == [("51272758", big)]
    for order in ([small, big], [big, small]):
        got = part_ids("51272758", MultiPolygon(order))
        assert [(sid, p.area) for sid, p in got] == [("51272758", 16.0), ("51272758/1", 1.0)]
    ids = [ncr_id("usa_structures", sid) for sid, _ in got]
    assert len(set(ids)) == 2 and ids[0] == ncr_id("usa_structures", "51272758")


def test_nc_county_table():
    from terratriage.ops.counties import NC_COUNTIES, county_name, county_of

    assert len(NC_COUNTIES) == 100
    # spot checks against the Census Bureau's county FIPS codes
    for fips, name in (("37001", "Alamance"), ("37021", "Buncombe"), ("37063", "Durham"),
                       ("37087", "Haywood"), ("37111", "McDowell"), ("37113", "Macon"),
                       ("37115", "Madison"), ("37119", "Mecklenburg"), ("37121", "Mitchell"),
                       ("37129", "New Hanover"), ("37161", "Rutherford"), ("37183", "Wake"),
                       ("37199", "Yancey")):
        assert NC_COUNTIES[fips] == name
    assert county_name("371119703001023") == "McDowell" and county_name("45045001") is None
    assert county_of(["371119703001023", "371119703001024", "370219801001000", None]) == "McDowell"
    assert county_of([]) == "" and county_of([None, "99"]) == ""


def test_repeated_source_ids_stay_unique():
    from shapely.geometry import box

    from terratriage.ops.pipeline import unique_id

    a, b, c = box(0, 0, 1, 1), box(5, 5, 6, 6), box(9, 9, 10, 10)
    taken = {}
    assert unique_id("77", a, taken) == "77"
    assert unique_id("77", box(0, 0, 1, 1), taken) is None       # the same feature, paged twice
    assert unique_id("77", b, taken) == "77~2"                   # a different building, same id
    assert unique_id("77", b, taken) is None
    assert unique_id("77", c, taken) == "77~3"
    assert unique_id("78", a, taken) == "78"
