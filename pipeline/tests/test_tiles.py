"""Imagery tiles for the Operations map, cut from an area's stored GeoTIFF."""
import io

import mercantile
import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from terratriage.ops.disseminate import tiles

# a 600 m square in UTM 17N (EPSG:6346, the ops storage grid) near Old Fort
E0, N0, RES, SIZE = 392_000.0, 3_944_000.0, 0.5, 1200


@pytest.fixture
def tif(tmp_path):
    p = tmp_path / "pre_2023-02-18.tif"
    arr = np.zeros((3, SIZE, SIZE), dtype="uint8")
    arr[0] = 200                       # red everywhere
    arr[1, : SIZE // 2] = 150          # green in the north half
    with rasterio.open(p, "w", driver="GTiff", width=SIZE, height=SIZE, count=3, dtype="uint8",
                       crs="EPSG:6346", transform=from_origin(E0, N0, RES, RES)) as ds:
        ds.write(arr)
    return str(p)


def _centre_lonlat():
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:6346", "EPSG:4326", always_xy=True).transform(
        E0 + SIZE * RES / 2, N0 - SIZE * RES / 2)


def _decode(body):
    return np.asarray(Image.open(io.BytesIO(body)).convert("RGBA"))


def test_interior_tile_is_a_full_jpeg(tif):
    lon, lat = _centre_lonlat()
    t = mercantile.tile(lon, lat, 18)
    body, media = tiles.render(tif, t.z, t.x, t.y)
    assert media == "image/jpeg"
    px = _decode(body)
    assert px.shape == (256, 256, 4) and abs(int(px[..., 0].mean()) - 200) <= 3


def test_north_is_up(tif):
    lon, lat = _centre_lonlat()
    t = mercantile.tile(lon, lat, 15)           # one tile holds the whole image
    px = _decode(tiles.render(tif, t.z, t.x, t.y)[0])
    rows = np.where(px[..., 3].any(axis=1))[0]
    cols = np.where(px[..., 3].any(axis=0))[0]
    top = px[rows[0] + 2, cols[len(cols) // 2]]
    bottom = px[rows[-1] - 2, cols[len(cols) // 2]]
    assert top[1] > 100 and bottom[1] < 50      # green half is the northern one


def test_edge_tile_is_transparent_outside_the_image(tif):
    lon, lat = _centre_lonlat()
    t = mercantile.tile(lon, lat, 15)
    body, media = tiles.render(tif, t.z, t.x, t.y)
    px = _decode(body)
    assert media == "image/png"
    covered = (px[..., 3] > 0).mean()
    assert 0.02 < covered < 0.6                 # 600 m of a ~1 km tile
    assert (px[px[..., 3] == 0][:, :3] == 0).all()


def test_tile_outside_the_image_is_none(tif):
    lon, lat = _centre_lonlat()
    t = mercantile.tile(lon + 0.5, lat, 16)
    assert tiles.render(tif, t.z, t.x, t.y) is None


def test_georeferencing_within_a_pixel(tif):
    """The image's NW corner lands where Web Mercator says it should."""
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:6346", "EPSG:4326", always_xy=True).transform(E0, N0)
    z = 17
    t = mercantile.tile(lon, lat, z)
    px = _decode(tiles.render(tif, t.z, t.x, t.y)[0])
    b = mercantile.xy_bounds(t)
    mx, my = mercantile.xy(lon, lat)
    col = (mx - b.left) / (b.right - b.left) * 256
    row = (b.top - my) / (b.top - b.bottom) * 256
    alpha = px[..., 3] > 0
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    assert abs(rows[0] - row) <= 1.5 and abs(cols[0] - col) <= 1.5


def test_cache_round_trip_and_staleness(tif, tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(tiles, "OPS_CACHE", str(tmp_path / "cache"))
    lon, lat = _centre_lonlat()
    t = mercantile.tile(lon, lat, 18)
    calls = []
    real = tiles.render
    monkeypatch.setattr(tiles, "render", lambda *a: calls.append(a) or real(*a))
    first = tiles.get("town", "pre", tif, t.z, t.x, t.y)
    again = tiles.get("town", "pre", tif, t.z, t.x, t.y)
    assert first == again and len(calls) == 1
    far = mercantile.tile(lon + 0.5, lat, 16)
    assert tiles.get("town", "pre", tif, far.z, far.x, far.y) is None
    assert tiles.get("town", "pre", tif, far.z, far.x, far.y) is None and len(calls) == 2
    os.utime(tif, (1, 1))                       # imagery re-fetched: new cache folder
    tiles.get("town", "pre", tif, t.z, t.x, t.y)
    assert len(calls) == 3
