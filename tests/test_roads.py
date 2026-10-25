import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from core.city_config import CityConfig
from core.roads import compute_road_risk_timeseries, fetch_road_network

CRS = "EPSG:32635"


def _write_lst_tif(path, region_values):
    """20x20, 10 m'lik sentetik bir LST rasteri yazar.

    `region_values`: [(row_slice, col_slice, value), ...] - geri kalan
    pikseller nodata (-9999.0) kalır, bu da gerçek bir sahnenin bulut/QA
    maskesiyle boşluklu kapsamını taklit eder.
    """
    grid = np.full((20, 20), -9999.0, dtype="float32")
    for rows, cols, value in region_values:
        grid[rows, cols] = value
    profile = {
        "driver": "GTiff", "height": 20, "width": 20, "count": 1, "dtype": "float32",
        "crs": CRS, "transform": from_origin(0, 200, 10, 10), "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(grid, 1)


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="testcity", name="Test City", bbox=[0.0, 0.0, 1.0, 1.0], crs=CRS,
        max_cloud_cover=30, osm_pbf_url="http://example.com/x.pbf",
        drive_highway_types=["primary", "secondary"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="cities.testcity.adapter",
    )


def test_refresh_osm_replaces_existing_extract_after_complete_download(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    pbf_path = raw_dir / "testcity.osm.pbf"
    pbf_path.parent.mkdir()
    pbf_path.write_bytes(b"old extract")
    monkeypatch.setattr("core.roads.city_data_raw", lambda city_id: raw_dir)
    monkeypatch.setattr("core.roads.resolve_pbf_path", lambda city_id: pbf_path)

    class _Response:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"new "
            yield b"extract"

    requests_seen = []
    monkeypatch.setattr("core.roads.requests.get", lambda *a, **kw: (requests_seen.append((a, kw)) or _Response()))
    monkeypatch.setattr(
        "core.roads.gpd.read_file",
        lambda *a, **kw: gpd.GeoDataFrame(
            {"name": ["A"], "highway": ["primary"]},
            geometry=[box(27, 38, 27.001, 38.001)], crs="EPSG:4326",
        ),
    )

    roads = fetch_road_network(_make_config(), refresh=True)

    assert len(requests_seen) == 1
    assert requests_seen[0][1]["stream"] is True
    assert pbf_path.read_bytes() == b"new extract"
    assert not (raw_dir / "testcity.osm.part.pbf").exists()
    assert len(roads) == 1


def test_failed_osm_refresh_preserves_existing_extract(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    pbf_path = raw_dir / "testcity.osm.pbf"
    pbf_path.parent.mkdir()
    pbf_path.write_bytes(b"known-good extract")
    monkeypatch.setattr("core.roads.city_data_raw", lambda city_id: raw_dir)
    monkeypatch.setattr("core.roads.resolve_pbf_path", lambda city_id: pbf_path)

    class _Response:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"incomplete"
            raise RuntimeError("simulated connection interruption")

    monkeypatch.setattr("core.roads.requests.get", lambda *a, **kw: _Response())

    with pytest.raises(RuntimeError, match="connection interruption"):
        fetch_road_network(_make_config(), refresh=True)

    assert pbf_path.read_bytes() == b"known-good extract"
    assert not (raw_dir / "testcity.osm.part.pbf").exists()


def _setup_two_roads(tmp_path, monkeypatch, constant=False):
    """Ortak ölçek ve `delta_lst` mantığını, gerçek OSM/uydu indirmesi
    olmadan doğrulamak için iki sahte yolu ve iki yıllık LST rasterini
    kurar (bkz. compute_road_risk_timeseries docstring'i).

    Road A: 2020'de 30, 2026'da 32 -> ısındı.
    Road B: 2020'de 20, 2026'da 19 -> soğudu (delta_lst == -1, sınır değeri).
    """
    proc_2020, proc_2026 = tmp_path / "proc" / "2020", tmp_path / "proc" / "2026"
    proc_2020.mkdir(parents=True)
    proc_2026.mkdir(parents=True)

    # Road A tamponu üstteki bölgeyi (satır 1-3, sütun 1-3), Road B tamponu
    # alttaki bölgeyi (satır 16-18, sütun 16-18) kapsayacak şekilde konumlandı.
    region_a = (slice(1, 4), slice(1, 4))
    region_b = (slice(16, 19), slice(16, 19))
    year_2020 = [(*region_a, 25.0), (*region_b, 25.0)] if constant else [(*region_a, 30.0), (*region_b, 20.0)]
    year_2026 = [(*region_a, 25.0), (*region_b, 25.0)] if constant else [(*region_a, 32.0), (*region_b, 19.0)]
    _write_lst_tif(proc_2020 / "lst_celsius.tif", year_2020)
    _write_lst_tif(proc_2026 / "lst_celsius.tif", year_2026)
    # NDVI de zonal_stats ile aynı çağrıda örneklenir; değeri bu testler
    # için önemsiz, tüm rasteri kaplayan sabit bir değer yeterli.
    _write_lst_tif(proc_2020 / "ndvi.tif", [(slice(0, 20), slice(0, 20), 0.3)])
    _write_lst_tif(proc_2026 / "ndvi.tif", [(slice(0, 20), slice(0, 20), 0.3)])

    road_a_buffer = box(10, 160, 40, 190)  # satır 1-3, sütun 1-3'ü kapsar
    road_b_buffer = box(160, 10, 190, 40)  # satır 16-18, sütun 16-18'i kapsar
    roads_gdf = gpd.GeoDataFrame({
        "name": ["Road A", "Road B"],
        "highway": ["primary", "secondary"],
        "length": [100.0, 100.0],
        "geometry": [road_a_buffer, road_b_buffer],
        "geometry_buffer": [road_a_buffer, road_b_buffer],
    }, crs=CRS)

    output_proc = tmp_path / "outproc"
    output_proc.mkdir()

    monkeypatch.setattr("core.roads.fetch_road_network", lambda config, refresh=False: roads_gdf.copy())
    monkeypatch.setattr(
        "core.roads.year_paths",
        lambda city_id, year, main_year: (tmp_path / "raw", proc_2020 if year == "2020" else proc_2026),
    )
    monkeypatch.setattr("core.roads.city_data_proc", lambda city_id: output_proc)


def test_risk_score_uses_common_scale_across_years(tmp_path, monkeypatch):
    # Yıllar ayrı ayrı min-max'a normalize edilseydi Road A ve Road B her
    # yılda kendi içinde 0/100'e denk gelirdi (her yılda sadece iki yol
    # var); ORTAK ölçekte 2020'nin en sıcak yolu (Road A, 30°C) 2026'nın en
    # sıcak yolundan (Road A, 32°C) daha düşük risk skoru almalı.
    _setup_two_roads(tmp_path, monkeypatch)
    config = _make_config()

    result = compute_road_risk_timeseries(config, ["2020", "2026"], "2026")
    by_name = result.set_index("name")

    assert by_name.loc["Road A", "risk_score_2020"] < by_name.loc["Road A", "risk_score_2026"]
    assert by_name.loc["Road A", "risk_score_2026"] == 100.0  # tüm yılların en sıcağı
    assert by_name.loc["Road B", "risk_score_2026"] == 0.0  # tüm yılların en soğuğu


def test_delta_lst_boundary_value_is_categorized_as_cooled(tmp_path, monkeypatch):
    # degisim_kategori sınırları [-100, -1, 1, 3, 100] - pd.cut varsayılanı
    # sağa kapalı aralıklar üretir, yani delta_lst == -1.0 tam sınırda
    # "Değişmedi" değil "Soğudu" kategorisine düşmeli. Bu, kodun kendisinin
    # zaten doğru yaptığı ama hiçbir testin doğrulamadığı bir sınır durumu.
    _setup_two_roads(tmp_path, monkeypatch)
    config = _make_config()

    result = compute_road_risk_timeseries(config, ["2020", "2026"], "2026")
    by_name = result.set_index("name")

    assert by_name.loc["Road B", "delta_lst"] == -1.0
    assert by_name.loc["Road B", "degisim_kategori"] == "Soğudu"
    assert by_name.loc["Road A", "degisim_kategori"] == "Hafif Isındı"


def test_road_with_no_valid_lst_in_any_year_is_dropped(tmp_path, monkeypatch):
    # Bir yolun tamponu rasterin kapsama alanı dışında kalırsa (ör. bulut
    # maskesi yüzünden tüm pikselleri nodata) `has_all_years` filtresi o
    # yolu sessizce dışarıda bırakmalı - NaN bir HVI bileşeni üretip
    # geometrik ortalamayı bozmak yerine.
    _setup_two_roads(tmp_path, monkeypatch)
    config = _make_config()

    roads_with_gap = gpd.GeoDataFrame({
        "name": ["Road A", "Road B", "Road C (no data)"],
        "highway": ["primary", "secondary", "residential"],
        "length": [100.0, 100.0, 100.0],
        "geometry": [box(10, 160, 40, 190), box(160, 10, 190, 40), box(500, 500, 530, 530)],
        "geometry_buffer": [box(10, 160, 40, 190), box(160, 10, 190, 40), box(500, 500, 530, 530)],
    }, crs=CRS)
    monkeypatch.setattr("core.roads.fetch_road_network", lambda config, refresh=False: roads_with_gap.copy())

    result = compute_road_risk_timeseries(config, ["2020", "2026"], "2026")

    assert "Road C (no data)" not in result["name"].tolist()
    assert len(result) == 2


def test_unsorted_years_are_compared_chronologically(tmp_path, monkeypatch):
    _setup_two_roads(tmp_path, monkeypatch)

    result = compute_road_risk_timeseries(_make_config(), ["2026", "2020"], "2026")
    road_a = result.set_index("name").loc["Road A"]

    assert road_a["delta_lst"] == 2.0


def test_single_year_is_rejected_for_timeseries(tmp_path, monkeypatch):
    import pytest

    with pytest.raises(ValueError, match="en az iki farklı yıl"):
        compute_road_risk_timeseries(_make_config(), ["2026"], "2026")


def test_constant_lst_range_returns_finite_neutral_risk_scores(tmp_path, monkeypatch):
    _setup_two_roads(tmp_path, monkeypatch, constant=True)

    result = compute_road_risk_timeseries(_make_config(), ["2020", "2026"], "2026")

    assert np.isfinite(result[["risk_score_2020", "risk_score_2026"]].to_numpy()).all()
    assert (result[["risk_score_2020", "risk_score_2026"]] == 0).all().all()
