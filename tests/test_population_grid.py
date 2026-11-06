import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

import core.population_grid as pg
from core.city_config import DEFAULT_POPULATION_GRID_URL, CityConfig, _population_grid_url, validate_config_dict

CRS = "EPSG:32635"
# ~33 m hücre: HRSL'nin 1 açı saniyelik ızgarasına yakın.
PIXEL = 0.0003


def _make_config(url: str | None = None) -> CityConfig:
    return CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.0, 27.06, 38.03], crs=CRS, max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused", population_grid_url=url,
    )


def _grid(width: int = 200, height: int = 100, west: float = 27.0, north: float = 38.03):
    return from_origin(west, north, PIXEL, PIXEL), (height, width)


def _write_grid(path, data: np.ndarray, transform) -> None:
    profile = {"driver": "GTiff", "height": data.shape[0], "width": data.shape[1], "count": 1,
               "dtype": "float32", "crs": "EPSG:4326", "transform": transform, "nodata": np.nan}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def _mahalle(rows: list[dict]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


# --- kalibrasyon birimleri ----------------------------------------------------

def test_neighbourhood_level_densities_stay_separate_units():
    # İzmir deseni: her mahallenin kendi yoğunluğu var.
    mahalle = _mahalle([
        {"ilce_adi": "A", "nufus_yogunlugu": 1000.0, "geometry": box(27.00, 38.00, 27.03, 38.03)},
        {"ilce_adi": "A", "nufus_yogunlugu": 3000.0, "geometry": box(27.03, 38.00, 27.06, 38.03)},
    ])
    units = pg.calibration_units(mahalle, CRS)
    assert len(units) == 2
    assert units["resmi_nufus"].iloc[1] / units["resmi_nufus"].iloc[0] == pytest.approx(3.0, rel=0.01)


def test_district_density_copied_to_neighbourhoods_becomes_one_unit():
    # TÜİK şablonu: ilçe yoğunluğu mahallelere kopyalanmış. Mahalle düzeyinde
    # kalibre etmek mahalle toplamlarını alanla orantılı yapardı.
    mahalle = _mahalle([
        {"ilce_adi": "A", "nufus_yogunlugu": 2000.0, "geometry": box(27.00, 38.00, 27.02, 38.03)},
        {"ilce_adi": "A", "nufus_yogunlugu": 2000.0, "geometry": box(27.02, 38.00, 27.04, 38.03)},
        {"ilce_adi": "B", "nufus_yogunlugu": 500.0, "geometry": box(27.04, 38.00, 27.06, 38.03)},
        {"ilce_adi": "B", "nufus_yogunlugu": np.nan, "geometry": box(27.06, 38.00, 27.07, 38.03)},
    ])
    units = pg.calibration_units(mahalle, CRS).set_index("birim")
    assert len(units) == 2
    area_a = mahalle.iloc[:2].to_crs(CRS).area.sum() / 1e6
    assert units["resmi_nufus"].filter(like="A|").iloc[0] == pytest.approx(2000.0 * area_a, rel=1e-6)


# --- dasimetrik kalibrasyon ---------------------------------------------------

def test_calibration_matches_official_totals_and_keeps_grid_distribution():
    transform, shape = _grid()
    grid = np.zeros(shape)
    grid[:, :50] = 1.0       # birim 1'in batı yarısı dolu
    grid[:, 50:100] = 3.0    # doğu yarısı üç kat dolu
    grid[:, 100:] = 2.0      # birim 2 düzgün
    grid[0, 0] = np.nan      # nodata hücresi toplamı bozmamalı
    units = gpd.GeoDataFrame(
        {"birim": ["u1", "u2"], "resmi_nufus": [8000.0, 500.0]},
        geometry=[box(27.0, 38.0, 27.03, 38.03), box(27.03, 38.0, 27.06, 38.03)], crs="EPSG:4326",
    )
    calibrated, report = pg.calibrate_grid(grid, transform, "EPSG:4326", units)

    assert np.nansum(calibrated[:, :100]) == pytest.approx(8000.0, rel=1e-4)
    assert np.nansum(calibrated[:, 100:]) == pytest.approx(500.0, rel=1e-4)
    # Birim içi oran ızgaradan gelir.
    assert calibrated[5, 60] / calibrated[5, 10] == pytest.approx(3.0, rel=1e-4)
    assert set(report.columns) >= {"birim", "resmi_nufus", "izgara_toplami", "kalibrasyon_carpani"}


def test_cells_outside_every_unit_are_nan_and_empty_unit_is_reported():
    transform, shape = _grid()
    grid = np.ones(shape)
    grid[:, 100:] = 0.0  # birim 2'de bina tespit edilmemiş
    units = gpd.GeoDataFrame(
        {"birim": ["u1", "u2"], "resmi_nufus": [100.0, 100.0]},
        geometry=[box(27.0, 38.0, 27.03, 38.03), box(27.03, 38.0, 27.05, 38.03)], crs="EPSG:4326",
    )
    calibrated, report = pg.calibrate_grid(grid, transform, "EPSG:4326", units)

    assert np.isnan(calibrated[:, -10:]).all()  # 27.05-27.06 hiçbir birimde değil
    assert report.set_index("birim").loc["u2", "izgara_toplami"] == 0
    assert np.nansum(calibrated[:, 100:166]) == 0


# --- yol örneklemesi ----------------------------------------------------------

def _roads_utm(xs: list[float], y: float = 38.015) -> gpd.GeoDataFrame:
    roads = gpd.GeoDataFrame(geometry=[LineString([(x, y), (x + 0.002, y)]) for x in xs], crs="EPSG:4326")
    return roads.to_crs(CRS)


def test_uniform_grid_density_is_recovered_on_roads():
    transform, shape = _grid()
    # Hücre başına 1 kişi: yoğunluk = 1 / hücre alanı.
    grid = np.ones(shape, dtype="float32")
    cell_area_km2 = gpd.GeoSeries([box(27.03, 38.015, 27.03 + PIXEL, 38.015 + PIXEL)], crs="EPSG:4326").to_crs(CRS).area.iloc[0] / 1e6
    density = pg.road_population_density(_roads_utm([27.02, 27.03]), grid, transform, "EPSG:4326", buffer_m=150)

    assert density.to_numpy() == pytest.approx(1 / cell_area_km2, rel=0.08)


def test_road_next_to_populated_cells_gets_higher_density_than_empty_area():
    transform, shape = _grid()
    grid = np.zeros(shape, dtype="float32")
    grid[:, :60] = 5.0
    density = pg.road_population_density(_roads_utm([27.005, 27.045]), grid, transform, "EPSG:4326", buffer_m=150)

    assert density.iloc[0] > 1000
    assert density.iloc[1] == 0


def test_chunking_does_not_change_the_result():
    transform, shape = _grid()
    rng = np.random.default_rng(0)
    grid = rng.random(shape).astype("float32")
    roads = _roads_utm([27.005 + 0.004 * i for i in range(12)])
    whole = pg.road_population_density(roads, grid, transform, "EPSG:4326", buffer_m=150)
    chunked = pg.road_population_density(roads, grid, transform, "EPSG:4326", buffer_m=150, chunk_size=5)
    assert chunked.tolist() == pytest.approx(whole.tolist())
    assert chunked.index.tolist() == roads.index.tolist()


# --- pencere okuma ve önbellek -----------------------------------------------

def test_fetch_reads_only_the_unit_window_and_reuses_cache(monkeypatch, tmp_path):
    transform, _ = from_origin(26.9, 38.1, PIXEL, PIXEL), None
    source = tmp_path / "global.tif"
    _write_grid(source, np.full((800, 1000), 2.0), transform)
    monkeypatch.setattr("core.population_grid.city_data_raw", lambda city_id: tmp_path / "raw")
    config = _make_config(str(source))

    path = pg.fetch_population_grid(config, (27.0, 38.0, 27.06, 38.03))
    with rasterio.open(path) as src:
        west, south, east, north = src.bounds
        assert west == pytest.approx(27.0 - pg.WINDOW_MARGIN_DEG, abs=PIXEL)
        assert north == pytest.approx(38.03 + pg.WINDOW_MARGIN_DEG, abs=PIXEL)
        assert src.width < 1000 and src.height < 800

    # Kaynak değişse de aynı pencere/adres için önbellek kullanılır.
    _write_grid(source, np.full((800, 1000), 9.0), transform)
    assert pg.fetch_population_grid(config, (27.0, 38.0, 27.06, 38.03)) == path
    with rasterio.open(path) as src:
        assert float(src.read(1)[0, 0]) == 2.0
    # force ile yeniden okunur.
    pg.fetch_population_grid(config, (27.0, 38.0, 27.06, 38.03), force=True)
    with rasterio.open(path) as src:
        assert float(src.read(1)[0, 0]) == 9.0


def test_fetch_refuses_when_grid_is_disabled(tmp_path):
    with pytest.raises(ValueError, match="kapalı"):
        pg.fetch_population_grid(_make_config(None), (27.0, 38.0, 27.06, 38.03))


# --- config ------------------------------------------------------------------

def _cfg(**extra) -> dict:
    return {
        "city": {"name": "X", "bbox": [27.0, 38.0, 27.2, 38.2], "crs": "EPSG:32635"},
        "osm": {"pbf_url": "u", "highway_types": ["residential"], "admin_level_ilce": 6, "admin_level_mahalle": 8},
        "population": {"adapter": "a"},
        **extra,
    }


def test_population_grid_defaults_on_and_can_be_disabled_or_overridden():
    assert _population_grid_url(_cfg()) == DEFAULT_POPULATION_GRID_URL
    assert _population_grid_url(_cfg(population_grid=False)) is None
    assert _population_grid_url(_cfg(population_grid={"url": " /yerel/izgara.tif "})) == "/yerel/izgara.tif"
    assert "latest" not in DEFAULT_POPULATION_GRID_URL


@pytest.mark.parametrize("value", [True, "url", {"url": ""}, {"kaynak": "x"}])
def test_invalid_population_grid_config_is_rejected(value):
    errors = validate_config_dict(_cfg(population_grid=value))
    assert any("population_grid" in error for error in errors)


def test_valid_population_grid_config_passes():
    assert validate_config_dict(_cfg(population_grid=False)) == []
    assert validate_config_dict(_cfg(population_grid={"url": "https://x/y.vrt"})) == []


def test_declared_district_units_fix_rural_dilution():
    # Eskişehir durumu: ilçe yoğunluğu kırsalı da içeren tüm ilçe alanına
    # bölünmüş. bbox yalnızca kentsel batı yarıyı kapsıyor. Ilçe birimi
    # verilince ızgara ilçenin tamamında resmi nüfusa ölçeklenir ve kentsel
    # kısım ızgaradaki payını alır (burada %90).
    transform, shape = _grid()
    grid = np.zeros(shape)
    grid[:, :100] = 9.0   # kentsel batı yarı: nüfusun %90'ı
    grid[:, 100:] = 1.0   # kırsal doğu yarı
    district = box(27.0, 38.0, 27.06, 38.03)
    official = 100000.0
    urban = _mahalle([{"ilce_adi": "A", "nufus_yogunlugu": official / (gpd.GeoSeries([district], crs="EPSG:4326")
                                                                       .to_crs(CRS).area.iloc[0] / 1e6),
                       "geometry": box(27.0, 38.0, 27.03, 38.03)}])
    naive = pg.calibration_units(urban, CRS)
    assert naive["resmi_nufus"].iloc[0] == pytest.approx(official / 2, rel=0.01)  # alanla orantılı: hatalı

    urban.attrs["nufus_birimleri"] = gpd.GeoDataFrame(
        {"birim": ["a"], "resmi_nufus": [official]}, geometry=[district], crs="EPSG:4326")
    units = pg.calibration_units(urban, CRS)
    calibrated, _ = pg.calibrate_grid(grid, transform, "EPSG:4326", units)
    assert np.nansum(calibrated) == pytest.approx(official, rel=1e-4)
    assert np.nansum(calibrated[:, :100]) == pytest.approx(0.9 * official, rel=1e-4)
