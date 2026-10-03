from dataclasses import dataclass, field

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from core.satellite import is_valid_geotiff, select_best_scenes_per_tile


# --- is_valid_geotiff: dosya var mı VE gerçekten açılabiliyor mu ---

def test_is_valid_geotiff_returns_false_for_missing_file(tmp_path):
    assert is_valid_geotiff(tmp_path / "yok.tif") is False


def test_is_valid_geotiff_returns_false_for_corrupt_file(tmp_path):
    # Yarıda kesilen bir indirme - dosya var ama geçerli bir GeoTIFF değil.
    corrupt = tmp_path / "bozuk.tif"
    corrupt.write_bytes(b"bu bir GeoTIFF degil")
    assert is_valid_geotiff(corrupt) is False


def test_is_valid_geotiff_returns_true_for_a_real_geotiff(tmp_path):
    path = tmp_path / "gecerli.tif"
    profile = {
        "driver": "GTiff", "height": 4, "width": 4, "count": 1, "dtype": "float32",
        "crs": "EPSG:32635", "transform": from_origin(0, 40, 10, 10), "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.zeros((4, 4), dtype="float32"), 1)
    assert is_valid_geotiff(path) is True


# --- select_best_scenes_per_tile: saf, network gerektirmeyen seçim mantığı ---

@dataclass
class _FakeItem:
    """pystac.Item'ın select_best_scenes_per_tile'ın kullandığı yüzeyi
    (`.id`, `.properties[...]`) - gerçek STAC/network olmadan test için."""
    id: str
    properties: dict = field(default_factory=dict)


def _fake_item(scene_id: str, wrs_path: int, wrs_row: int, cloud_cover: float) -> _FakeItem:
    return _FakeItem(scene_id, {
        "landsat:wrs_path": wrs_path, "landsat:wrs_row": wrs_row, "eo:cloud_cover": cloud_cover,
    })


def test_select_best_scenes_per_tile_default_matches_old_single_scene_behavior():
    # max_per_tile=1 (varsayılan) - önceki min(..., key=cloud_cover)
    # davranışıyla birebir aynı olmalı (regresyon güvencesi).
    items = [
        _fake_item("a", 180, 33, 20.0),
        _fake_item("b", 180, 33, 5.0),   # en temiz - bu seçilmeli
        _fake_item("c", 180, 33, 15.0),
        _fake_item("d", 181, 33, 8.0),   # farklı karo - ayrı seçilir
    ]

    result = select_best_scenes_per_tile(items, max_per_tile=1)

    assert [i.id for i in result[(180, 33)]] == ["b"]
    assert [i.id for i in result[(181, 33)]] == ["d"]


def test_select_best_scenes_per_tile_returns_top_n_sorted_by_cloud_cover():
    items = [
        _fake_item("a", 180, 33, 20.0),
        _fake_item("b", 180, 33, 5.0),
        _fake_item("c", 180, 33, 15.0),
        _fake_item("d", 180, 33, 1.0),
        _fake_item("e", 180, 33, 30.0),
    ]

    result = select_best_scenes_per_tile(items, max_per_tile=3)

    assert [i.id for i in result[(180, 33)]] == ["d", "b", "c"]


def test_select_best_scenes_per_tile_returns_fewer_than_max_if_not_enough_candidates():
    items = [_fake_item("a", 180, 33, 10.0), _fake_item("b", 180, 33, 5.0)]

    result = select_best_scenes_per_tile(items, max_per_tile=5)

    assert len(result[(180, 33)]) == 2


def test_select_best_scenes_per_tile_treats_missing_cloud_cover_as_worst():
    items = [_fake_item("a", 180, 33, 10.0), _FakeItem("b", {"landsat:wrs_path": 180, "landsat:wrs_row": 33})]

    result = select_best_scenes_per_tile(items, max_per_tile=1)

    assert [i.id for i in result[(180, 33)]] == ["a"]


def test_select_best_scenes_per_tile_empty_input_returns_empty_dict():
    assert select_best_scenes_per_tile([], max_per_tile=1) == {}


# --- fetch_landsat_scenes: arama penceresi config'ten gelmeli ---------------

def test_fetch_landsat_scenes_searches_configured_season(monkeypatch, tmp_path):
    from core import satellite
    from core.city_config import CityConfig

    config = CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.0, 27.5, 38.5], crs="EPSG:32635", max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
        season_start="06-01", season_end="09-15",
    )
    captured = {}

    class _Search:
        def items(self):
            return []

    class _Catalog:
        def search(self, **kwargs):
            captured.update(kwargs)
            return _Search()

    monkeypatch.setattr("core.satellite.pystac_client.Client.open", lambda *args, **kwargs: _Catalog())
    monkeypatch.setattr("core.satellite.year_paths", lambda city_id, year, main_year: (tmp_path, tmp_path))

    # Aday sahne olmadığı için hata beklenir; önemli olan sorgunun penceresi.
    with pytest.raises(RuntimeError):
        satellite.fetch_landsat_scenes(config, "2024", "2024")
    assert captured["datetime"] == "2024-06-01/2024-09-15"


# --- download_band: süresi dolmuş imzayla indirmeye çalışmamalı --------------

def test_download_band_resigns_url_instead_of_reusing_search_time_token(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from core import satellite

    # Arama anında imzalanmış (ve bu arada süresi dolmuş olabilecek) adres.
    item = SimpleNamespace(assets={"red": SimpleNamespace(href="https://blob.example/B4.TIF?se=eski&sig=eski")})
    signed, requested = [], []

    def fake_sign(url):
        signed.append(url)
        return url + "?sig=taze"

    class _Response:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            return [b"veri"]

    def fake_get(url, **kwargs):
        requested.append(url)
        return _Response()

    monkeypatch.setattr("core.satellite.planetary_computer.sign", fake_sign)
    monkeypatch.setattr("core.satellite.requests.get", fake_get)

    satellite.download_band(item, "red", tmp_path / "b4.tif")

    assert signed == ["https://blob.example/B4.TIF"]
    assert requested == ["https://blob.example/B4.TIF?sig=taze"]
    assert (tmp_path / "b4.tif").read_bytes() == b"veri"
