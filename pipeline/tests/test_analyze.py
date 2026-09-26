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
    v = decide([Channel("E1", True, L, 1.0), Channel("E5", True, L, 1.0)])
    assert FEMA[v.label] == "destroyed" and not v.needs_review
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
