from datetime import date

import pytest
from shapely.geometry import box

from terratriage.ops.cachekey import cache_key
from terratriage.ops.plan import events as ev


def _decl(fixture_json):
    return ev.parse_declaration(fixture_json("openfema_dr4827_2026-09-26.json"), "fixture")


def test_dr4827_parsed_from_openfema(fixture_json):
    d = _decl(fixture_json)
    assert d.fema_id == "DR-4827-NC"
    assert d.incident_begin == date(2024, 9, 25)
    assert d.declared == date(2024, 9, 28)
    assert "McDowell (County)" in d.designated_areas


def test_registry_windows_hold(fixture_json):
    import yaml
    from terratriage.ops import CONFIG_DIR
    cfg = yaml.safe_load(open(f"{CONFIG_DIR}/events.yaml"))
    for eid, spec in cfg["events"].items():
        e = ev.build_event(eid, spec, [_decl(fixture_json)])
        assert e.pre.end < e.incident_begin <= e.post.start
        assert not ({a.id for a in e.tune_aois()} & {a.id for a in e.test_aois()})


def test_original_helene_misdating_fails(fixture_json):
    # v2 bug: event date inferred as 2021-01 -> both images were pre-event
    d = _decl(fixture_json)
    with pytest.raises(ev.WindowError):
        ev.check_image_pair(date(2020, 11, 1), date(2022, 1, 7), d.incident_begin, "helene-v2-bug")
    with pytest.raises(ev.WindowError):
        ev.check_windows(ev.Window(date(2020, 1, 1), date(2024, 9, 26)),
                         ev.Window(date(2024, 9, 27), date(2024, 11, 1)), d.incident_begin)


def test_old_fort_pair_is_valid(fixture_json):
    ev.check_image_pair(date(2022, 1, 7), date(2024, 10, 2), _decl(fixture_json).incident_begin)


def test_same_name_different_geometry_different_key():
    a = cache_key("osm_buildings", geometry=box(-82.19, 35.62, -82.17, 35.64), params={"area": "old_fort"})
    b = cache_key("osm_buildings", geometry=box(-82.09, 35.90, -82.06, 35.92), params={"area": "old_fort"})
    assert a != b


def test_cache_key_stable_and_precision_normalized():
    a = cache_key("x", geometry=(-82.19, 35.62, -82.17, 35.64), time_window=("2024-09-25", None))
    b = cache_key("x", geometry=(-82.190000001, 35.62, -82.17, 35.64), time_window=("2024-09-25", None))
    assert a == b and len(a) == 64
    assert cache_key("x", dataset_version="2026-09-17.0") != cache_key("x", dataset_version="2026-08-20.0")


def test_bad_role_rejected(fixture_json):
    spec = {"name": "x", "windows": {"pre_days": [-10, -1], "post_days": [0, 5]},
            "aois": {"a": {"role": "TRAIN", "center": [0, 0]}}}
    with pytest.raises(ValueError):
        ev.build_event("x", spec, [_decl(fixture_json)])


@pytest.mark.live
def test_openfema_live():
    d = ev.fetch_declaration(4827, max_age_s=0)
    assert d.incident_begin == date(2024, 9, 25)
