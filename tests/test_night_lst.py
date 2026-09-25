import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

import core.night_lst as night_lst
from core.cache import write_cache_meta
from core.city_config import CityConfig
from core.night_lst import (
    NIGHT_LST_RASTER_VERSION,
    NEIGHBORHOOD_NIGHT_LST_VERSION,
    _raw_to_celsius,
    compute_neighborhood_night_lst,
    fetch_night_lst,
)

CRS = "EPSG:32635"


# --- _raw_to_celsius: saf ölçek dönüşümü, network gerektirmez ---

def test_raw_to_celsius_applies_kelvin_scale_and_offset():
    raw = np.array([15000.0], dtype=np.float32)  # 15000 * 0.02 = 300 K = 26.85 °C
    result = _raw_to_celsius(raw)
    assert np.isclose(result[0], 26.85, atol=0.01)


def test_raw_to_celsius_treats_zero_as_missing_data():
    # Ürün belgesine göre ham 0 = geçersiz/veri yok - gerçek bir ölçümle
    # (ör. çok soğuk bir gece) karışmamalı, NaN olmalı.
    raw = np.array([0.0, 15000.0], dtype=np.float32)
    result = _raw_to_celsius(raw)
    assert np.isnan(result[0])
    assert not np.isnan(result[1])


def test_raw_to_celsius_preserves_array_shape():
    raw = np.array([[0.0, 14000.0], [16000.0, 0.0]], dtype=np.float32)
    result = _raw_to_celsius(raw)
    assert result.shape == (2, 2)


# --- compute_neighborhood_night_lst: pbf + zaten indirilmiş raster okur, network gerektirmez ---

def _make_config() -> CityConfig:
    return CityConfig(
        city_id="testcity", name="Test City", bbox=[0.0, 0.0, 1.0, 1.0], crs=CRS,
        max_cloud_cover=30, osm_pbf_url="http://example.com/x.pbf",
        drive_highway_types=["primary"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="cities.testcity.adapter",
    )


def _write_night_lst_tif(path):
    """20x20, 10 m'lik sentetik bir gece LST rasteri - üst yarı 18°C,
    alt yarı 24°C, kalanı nodata."""
    grid = np.full((20, 20), -9999.0, dtype="float32")
    grid[2:8, 2:8] = 18.0
    grid[12:18, 12:18] = 24.0
    profile = {
        "driver": "GTiff", "height": 20, "width": 20, "count": 1, "dtype": "float32",
        "crs": CRS, "transform": from_origin(0, 200, 10, 10), "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(grid, 1)


def test_compute_neighborhood_night_lst_averages_per_mahalle(tmp_path, monkeypatch):
    night_tif = tmp_path / "night_lst_2026.tif"
    _write_night_lst_tif(night_tif)

    mahalle_gdf = gpd.GeoDataFrame({
        "name": ["Serin Mahalle", "Sicak Mahalle", "Yol (mahalle degil)"],
        "admin_level": ["8", "8", "6"],
        "boundary": ["administrative", "administrative", "administrative"],
        "geometry": [box(10, 130, 90, 190), box(110, 10, 190, 90), box(0, 0, 200, 200)],
    }, crs=CRS)
    monkeypatch.setattr(night_lst.gpd, "read_file", lambda *a, **kw: mahalle_gdf)

    output_proc = tmp_path / "outproc"
    output_proc.mkdir()
    monkeypatch.setattr("core.night_lst.city_data_proc", lambda city_id: output_proc)

    config = _make_config()
    out_path = compute_neighborhood_night_lst(config, "dummy.pbf", night_tif, "2026")

    # gpd.read_file testin başında monkeypatch'lendiği için (mahalle
    # poligonlarını sahtelemek amacıyla), üretilen çıktıyı okumadan önce
    # geri alınmalı - aksi halde bu satır da sahte veriyi döner.
    monkeypatch.undo()
    result = gpd.read_file(out_path)
    by_name = result.set_index("mahalle_adi")

    # admin_level "6" olan poligon ("Yol") admin_level_mahalle == "8"
    # filtresiyle tamamen dışarıda bırakılmalı.
    assert "Yol (mahalle degil)" not in by_name.index
    assert by_name.loc["Serin Mahalle", "gece_lst_c"] == 18.0
    assert by_name.loc["Sicak Mahalle", "gece_lst_c"] == 24.0


def test_compute_neighborhood_night_lst_drops_mahalle_with_no_valid_pixels(tmp_path, monkeypatch):
    night_tif = tmp_path / "night_lst_2026.tif"
    _write_night_lst_tif(night_tif)

    mahalle_gdf = gpd.GeoDataFrame({
        "name": ["Veri Yok Mahalle"],
        "admin_level": ["8"],
        "boundary": ["administrative"],
        # Rasterin tamamen dışında bir poligon - zonal_stats mean=None döner.
        "geometry": [Polygon([(1000, 1000), (1010, 1000), (1010, 1010), (1000, 1010)])],
    }, crs=CRS)
    monkeypatch.setattr(night_lst.gpd, "read_file", lambda *a, **kw: mahalle_gdf)

    output_proc = tmp_path / "outproc"
    output_proc.mkdir()
    monkeypatch.setattr("core.night_lst.city_data_proc", lambda city_id: output_proc)

    config = _make_config()
    out_path = compute_neighborhood_night_lst(config, "dummy.pbf", night_tif, "2026")

    monkeypatch.undo()
    result = gpd.read_file(out_path)
    assert len(result) == 0


def test_fetch_night_lst_cache_requires_current_version_and_respects_force(tmp_path, monkeypatch):
    output_dir = tmp_path / "processed"
    output_dir.mkdir()
    out_path = output_dir / "night_lst_2026.tif"
    out_path.write_bytes(b"cached")
    monkeypatch.setattr("core.night_lst.city_data_proc", lambda city_id: output_dir)
    monkeypatch.setattr(
        night_lst.pystac_client.Client,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cache rebuild requested")),
    )

    write_cache_meta(out_path, NIGHT_LST_RASTER_VERSION)
    assert fetch_night_lst(_make_config(), "2026") == out_path

    write_cache_meta(out_path, NIGHT_LST_RASTER_VERSION - 1)
    with pytest.raises(RuntimeError, match="cache rebuild requested"):
        fetch_night_lst(_make_config(), "2026")

    write_cache_meta(out_path, NIGHT_LST_RASTER_VERSION)
    with pytest.raises(RuntimeError, match="cache rebuild requested"):
        fetch_night_lst(_make_config(), "2026", force=True)


def test_neighborhood_night_lst_cache_requires_current_version_and_respects_force(tmp_path, monkeypatch):
    output_dir = tmp_path / "processed"
    output_dir.mkdir()
    out_path = output_dir / "night_lst_by_mahalle_2026.geojson"
    out_path.write_text("cached", encoding="utf-8")
    monkeypatch.setattr("core.night_lst.city_data_proc", lambda city_id: output_dir)
    monkeypatch.setattr(
        night_lst.gpd,
        "read_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cache rebuild requested")),
    )

    write_cache_meta(out_path, NEIGHBORHOOD_NIGHT_LST_VERSION)
    assert compute_neighborhood_night_lst(
        _make_config(), Path("dummy.pbf"), Path("night_lst.tif"), "2026"
    ) == out_path

    write_cache_meta(out_path, NEIGHBORHOOD_NIGHT_LST_VERSION - 1)
    with pytest.raises(RuntimeError, match="cache rebuild requested"):
        compute_neighborhood_night_lst(
            _make_config(), Path("dummy.pbf"), Path("night_lst.tif"), "2026"
        )

    write_cache_meta(out_path, NEIGHBORHOOD_NIGHT_LST_VERSION)
    with pytest.raises(RuntimeError, match="cache rebuild requested"):
        compute_neighborhood_night_lst(
            _make_config(), Path("dummy.pbf"), Path("night_lst.tif"), "2026", force=True
        )
