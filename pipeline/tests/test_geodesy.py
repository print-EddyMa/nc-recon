import math

import pytest
from pyproj import CRS

from terratriage.ops import geodesy as g
from terratriage.ops import heights as h

OLD_FORT = (-82.1804, 35.6293)


@pytest.mark.parametrize("role", sorted(g.DEFAULT_REGISTRY))
def test_every_registry_crs_resolves(role):
    assert CRS.from_epsg(g.registry()[role])


@pytest.mark.parametrize("role", ["nc_metric", "nc_ftus", "nc_legacy_m", "nc_legacy_ftus",
                                  "nc_harn", "utm17", "equal_area", "display"])
def test_round_trip_projected(role):
    lon, lat = OLD_FORT
    fwd = g.transformer("storage", role)
    inv = g.transformer(role, "storage")
    x, y = fwd.transform(lon, lat)
    lon2, lat2 = inv.transform(x, y)
    assert abs(lon2 - lon) < 1e-8 and abs(lat2 - lat) < 1e-8


def test_old_fort_nad83_2011_vs_itrf2014_offset():
    # Phase J spec: ~1.16 m horizontal, ~1.33 m vertical at epoch 2026.7 (+-5 cm)
    off = g.nad83_2011_to_itrf2014(*OLD_FORT, 400.0, 2026.7)
    assert abs(off.horizontal_m - 1.16) < 0.05
    assert abs(abs(off.vertical_m) - 1.33) < 0.05
    assert "ballpark" not in off.operation.lower()


def test_offset_grows_with_time():
    a = g.nad83_2011_to_itrf2014(*OLD_FORT, 400.0, 2010.0).horizontal_m
    b = g.nad83_2011_to_itrf2014(*OLD_FORT, 400.0, 2026.7).horizontal_m
    assert b > a


def test_us_survey_foot_vs_international_foot():
    # 2 ppm: a 2,100,000 ft easting differs by ~4.2 ft
    e = 2_100_000
    diff_ft = (g.ftus_to_m(e) - g.ft_to_m(e)) / g.INTL_FOOT_M
    assert abs(diff_ft - 4.2) < 0.05
    assert g.crs_linear_unit(6543) == "US survey foot"
    assert g.crs_linear_unit(6542) == "metre"


def test_axis_order_guard():
    g.assert_lonlat_in_nc(*OLD_FORT)
    with pytest.raises(ValueError, match="axis order"):
        g.assert_lonlat_in_nc(OLD_FORT[1], OLD_FORT[0])


def test_every_projected_nc_point_lands_in_nc():
    lon, lat = OLD_FORT
    for role in ("nc_metric", "nc_ftus", "utm17"):
        x, y = g.transformer("storage", role).transform(lon, lat)
        lon2, lat2 = g.transformer(role, "storage").transform(x, y)
        assert g.in_nc(lon2, lat2)


def test_refuse_measuring_in_web_mercator():
    with pytest.raises(ValueError, match="Web Mercator"):
        g.assert_measurable(3857)
    with pytest.raises(ValueError, match="geographic"):
        g.assert_measurable(4326)
    g.assert_measurable(6542)


def test_web_mercator_distortion_is_real():
    # a 1 km east-west segment at Old Fort measures ~1.23 km in EPSG:3857
    lon, lat = OLD_FORT
    dlon = 1000 / (111320 * math.cos(math.radians(lat)))
    t = g.transformer("storage", "display")
    x1, _ = t.transform(lon, lat)
    x2, _ = t.transform(lon + dlon, lat)
    assert 1.2 < (x2 - x1) / 1000 < 1.26


def test_usng_round_trip():
    s1 = g.usng(*OLD_FORT, precision_m=1)
    s10 = g.usng(*OLD_FORT, precision_m=10)
    assert s1.startswith("17S ") and len(s1.split()) == 4
    assert len(s10.split()[2]) == 4
    lon, lat = g.usng_to_lonlat(s1)
    assert g.distance_m(lon, lat, *OLD_FORT) < 2.0


def test_equal_area_area():
    from shapely.geometry import box
    lon, lat = OLD_FORT
    d = 0.001
    a = g.area_m2(box(lon, lat, lon + d, lat + d))
    assert 8_000 < a < 11_000


def test_crs_config_override(tmp_path, monkeypatch):
    # NSRS 2022 readiness: a placeholder "2022 frame" swaps in via config only
    import terratriage.ops.geodesy as geo
    (tmp_path / "crs.yaml").write_text("crs:\n  nc_metric: 32119\n")
    monkeypatch.setattr(geo, "CONFIG_DIR", str(tmp_path))
    geo.registry.cache_clear()
    try:
        assert geo.registry()["nc_metric"] == 32119
    finally:
        monkeypatch.undo()
        geo.registry.cache_clear()


# ---------------------------- typed heights ------------------------------ #
def test_stage_plus_elevation_raises():
    stage = h.GaugeStage.of(16.2, "02084000")
    elev = h.Elevation.of(12.7, "ft")
    with pytest.raises(h.HeightTypeError):
        _ = stage + elev
    with pytest.raises(h.HeightTypeError):
        _ = elev + stage


def test_stages_from_different_gauges_not_comparable():
    with pytest.raises(h.HeightTypeError):
        _ = h.GaugeStage.of(10, "A") < h.GaugeStage.of(12, "B")


def test_stage_to_elevation_and_depth():
    datum = h.Elevation.of(-3.5, "ft")          # gauge datum in NAVD88
    wse = h.GaugeStage.of(16.2, "tar_greenville").to_elevation(datum)
    assert abs(wse.to("ft") - 12.7) < 1e-9
    ground = h.Elevation.of(10.0, "ft")
    d = wse.minus(ground)
    assert isinstance(d, h.Depth) and abs(d.to("ft") - 2.7) < 1e-9


def test_geoid_step():
    gnss = h.EllipsoidalHeight.of(370.0, "m")
    H = gnss.to_navd88(geoid_undulation_m=-32.0)
    assert abs(H.m - 402.0) < 1e-9
    with pytest.raises(h.HeightTypeError):
        h.EllipsoidalHeight.of(370.0, "m", frame="ITRF2014").to_navd88(-32.0)


def test_datum_mismatch():
    with pytest.raises(h.HeightTypeError):
        h.Elevation.of(1, datum="NAVD88").minus(h.Elevation.of(1, datum="NGVD29"))
