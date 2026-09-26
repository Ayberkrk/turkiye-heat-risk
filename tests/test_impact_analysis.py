import json
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import LineString

import core.impact_analysis as ia
from core.city_config import CityConfig

CRS = "EPSG:32635"
BBOX = [27.00, 38.40, 27.03, 38.42]
YEARS = ["2020", "2022", "2024"]


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="testcity", name="Test City", bbox=list(BBOX), crs=CRS,
        max_cloud_cover=30, osm_pbf_url="http://example.com/x.pbf",
        drive_highway_types=["primary"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="cities.testcity.adapter",
    )


# --- saf yardımcılar ---

def test_normalize_scales_to_unit_interval_and_clips_to_given_bounds():
    result = ia._normalize(pd.Series([0.0, 5.0, 10.0, 20.0]), 0.0, 10.0)
    assert result.tolist() == [0.0, 0.5, 1.0, 1.0]


def test_normalize_constant_series_is_all_zero_not_nan():
    # max == min iken sıfıra bölme NaN üretirdi; skor hattı bunu sessizce dışlardı.
    assert ia._normalize(pd.Series([3.0, 3.0, 3.0])).tolist() == [0.0, 0.0, 0.0]


def test_weights_sum_to_one_and_follow_profile_order():
    components = ["hazard_norm", "sensitivity_agac_norm", "sensitivity_yasli_norm"]
    equal = ia._weights("equal", components)
    heat = ia._weights("heat_priority", components)
    assert np.isclose(equal.sum(), 1.0) and np.allclose(equal, 1 / 3)
    assert np.isclose(heat.sum(), 1.0)
    assert heat[0] > heat[2]  # ısı öncelikli profilde tehlike, yaşlı oranından ağır


def test_active_components_include_optional_columns_only_when_present():
    roads = pd.DataFrame({"exposure_norm": [0.1], "sensitivity_yasli_norm": [0.2]})
    assert ia._active_components(roads) == [
        "hazard_norm", "sensitivity_agac_norm", "exposure_norm", "sensitivity_yasli_norm",
    ]


def test_weather_grid_is_inside_bbox_with_expected_cell_count():
    grid = ia._weather_grid(_make_config())
    assert len(grid) == ia.WEATHER_GRID[0] * ia.WEATHER_GRID[1]
    for lat, lon in grid:
        assert BBOX[1] < lat < BBOX[3] and BBOX[0] < lon < BBOX[2]


def test_nearest_grid_assigns_each_road_to_closest_cell():
    grid = [(38.40, 27.00), (38.42, 27.03)]
    roads = gpd.GeoDataFrame(
        geometry=[
            LineString([(27.000, 38.401), (27.001, 38.401)]),
            LineString([(27.029, 38.419), (27.030, 38.419)]),
        ],
        crs="EPSG:4326",
    )
    assert ia._nearest_grid_for_roads(roads, grid, CRS).tolist() == [0, 1]


def test_scores_for_buffer_equal_profile_is_floored_geometric_mean():
    roads = pd.DataFrame({"exposure_norm": [0.5, 0.5]})
    lst = {"2020": pd.Series([10.0, 30.0])}
    ndvi = {"2020": pd.Series([0.2, 0.2])}
    score = ia._scores_for_buffer(roads, ["2020"], lst, ndvi, "equal")["2020"]
    floor = ia.COMPONENT_FLOOR

    def f(x):
        return floor + (1 - floor) * x

    # LST 10 -> 0, LST 30 -> 1; NDVI sabit (min == max) -> yeşil bileşeni 1 - 0 = 1
    expected_low = np.exp(np.mean(np.log([f(0.0), f(1.0), f(0.5)]))) * 100
    expected_high = np.exp(np.mean(np.log([f(1.0), f(1.0), f(0.5)]))) * 100
    assert np.isclose(score.iloc[0], expected_low)
    assert np.isclose(score.iloc[1], expected_high)
    assert score.iloc[1] > score.iloc[0]


def test_scores_for_buffer_leaves_roads_with_missing_component_nan():
    roads = pd.DataFrame({"exposure_norm": [0.5, np.nan]})
    lst = {"2020": pd.Series([10.0, 30.0])}
    ndvi = {"2020": pd.Series([0.2, 0.4])}
    score = ia._scores_for_buffer(roads, ["2020"], lst, ndvi, "equal")["2020"]
    assert score.notna().tolist() == [True, False]


def test_summarize_robustness_identical_scores_give_perfect_agreement():
    scores = {"2024": pd.Series(np.arange(20, dtype=float))}
    row = ia._summarize_robustness(None, ["2024"], scores, "equal", 10, scores)
    assert row["spearman_rank_correlation"] == 1.0
    assert row["top_decile_overlap_pct"] == 100.0
    assert row["valid_road_count"] == 20


def test_summarize_robustness_reversed_ranking_has_no_top_overlap():
    base = {"2024": pd.Series(np.arange(20, dtype=float))}
    reversed_scores = {"2024": pd.Series(np.arange(20, dtype=float)[::-1].copy())}
    row = ia._summarize_robustness(None, ["2024"], reversed_scores, "equal", 10, base)
    assert row["spearman_rank_correlation"] == -1.0
    assert row["top_decile_overlap_pct"] == 0.0


# --- ERA5-Land: hava anomalisi ---

def _daily_location(observed_day: str, observed_value: float) -> dict:
    """1991-2022 arası her gün 25 °C; yalnızca sahne günü `observed_value`."""
    days = pd.date_range("1991-06-24", "2022-09-07", freq="D")
    temps = [25.0] * len(days)
    location = {"daily": {
        "time": [d.strftime("%Y-%m-%d") for d in days],
        "temperature_2m_mean": temps,
    }}
    index = location["daily"]["time"].index(observed_day)
    location["daily"]["temperature_2m_mean"][index] = observed_value
    return location


def test_temperature_anomaly_is_scene_day_minus_baseline_normal(monkeypatch):
    config = _make_config()
    grid = ia._weather_grid(config)
    # 2022 taban dönemin (1991-2020) dışında: normal yalnızca 25 °C günlerden gelir.
    locations = [_daily_location("2022-07-15", 29.0) for _ in grid]
    monkeypatch.setattr(ia, "_load_weather", lambda cfg, years: (locations, grid))
    monkeypatch.setattr(ia, "_scene_dates", lambda city, year, main: ["2022-07-15"])

    by_year, _, detail = ia._temperature_anomalies(config, ["2022"], "2022")
    assert np.allclose(by_year["2022"], 4.0)
    assert set(detail["air_temperature_anomaly_c"]) == {4.0}


def test_temperature_anomaly_is_nan_when_scene_day_missing(monkeypatch):
    config = _make_config()
    grid = ia._weather_grid(config)
    locations = [_daily_location("2022-07-15", 29.0) for _ in grid]
    monkeypatch.setattr(ia, "_load_weather", lambda cfg, years: (locations, grid))
    monkeypatch.setattr(ia, "_scene_dates", lambda city, year, main: ["2023-07-15"])

    by_year, _, detail = ia._temperature_anomalies(config, ["2023"], "2023")
    assert np.isnan(by_year["2023"]).all()
    assert detail.empty


def test_load_weather_caches_response_and_validates_location_count(monkeypatch, tmp_path):
    config = _make_config()
    monkeypatch.setattr(ia, "city_data_raw", lambda city_id: tmp_path)
    grid = ia._weather_grid(config)
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    payload = [{"daily": {"time": [], "temperature_2m_mean": []}} for _ in grid]

    def fake_get(url, params, timeout):
        calls.append(params)
        return FakeResponse(payload)

    monkeypatch.setattr(ia.requests, "get", fake_get)
    first, _ = ia._load_weather(config, ["2020", "2024"])
    second, _ = ia._load_weather(config, ["2020", "2024"])
    assert len(first) == len(second) == len(grid)
    assert len(calls) == 1  # ikinci çağrı önbellekten
    assert calls[0]["end_date"] == "2024-09-07"

    payload.pop()
    monkeypatch.setattr(ia, "city_data_raw", lambda city_id: tmp_path / "bos")
    with pytest.raises(ValueError, match="konum"):
        ia._load_weather(config, ["2020", "2024"])


# --- senaryolar ---

def _scenario_inputs(n=10):
    roads = pd.DataFrame({
        "exposure_norm": np.linspace(0.1, 0.9, n),
        "sensitivity_yasli_norm": np.linspace(0.9, 0.1, n),
        "yasli_oran": np.linspace(0.05, 0.25, n),
        "nufus_yogunlugu": np.linspace(100, 1000, n),
    })
    roads = gpd.GeoDataFrame(
        roads, geometry=[LineString([(27 + i * 0.001, 38.4), (27 + i * 0.001, 38.401)]) for i in range(n)],
        crs="EPSG:4326",
    ).to_crs(CRS)
    lst = {"2024": pd.Series(np.linspace(30.0, 45.0, n))}
    ndvi = {"2024": pd.Series(np.linspace(0.6, 0.1, n))}
    base = ia._scores_for_buffer(roads, ["2024"], lst, ndvi, "equal")
    bounds = {"lst": (30.0, 45.0), "ndvi": (0.1, 0.6)}
    return roads, lst, ndvi, base, bounds


def test_intervention_scenarios_only_change_targeted_roads_and_lower_risk():
    roads, lst, ndvi, base, bounds = _scenario_inputs()
    output, table = ia._make_impact_geodata(
        roads, ["2024"], base, base, lst["2024"], ndvi["2024"], bounds,
        target_share=0.2, cooling_c=2.0, ndvi_delta=0.15,
    )
    targeted = output["targeted_for_scenario"].astype(bool)
    assert targeted.sum() == 2
    # Hedef: son yıl HVI sıralamasındaki en riskli yollar
    assert set(output.index[targeted]) == set(base["2024"].nlargest(2).index)
    for scenario in ("trees", "shade", "combined"):
        delta = output[f"hvi_{scenario}"] - output["hvi_base_2024"]
        assert np.allclose(delta[~targeted], 0.0, atol=1e-9)
        assert (delta[targeted] < 0).all()
    combined = table.set_index("scenario")["mean_hvi_delta_target"]
    assert combined["combined"] < combined["shade"] < 0
    assert combined["combined"] < combined["trees"] < 0
    assert table.loc[table["scenario"] == "base", "mean_hvi_delta_target"].iloc[0] == 0.0


# --- uçtan uca ---

def _write_rasters(proc_dir, year_offset):
    to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    west, south = to_utm.transform(BBOX[0] - 0.005, BBOX[1] - 0.005)
    east, north = to_utm.transform(BBOX[2] + 0.005, BBOX[3] + 0.005)
    width, height = int((east - west) / 10), int((north - south) / 10)
    x_ramp = np.linspace(0.0, 1.0, width, dtype="float32")[None, :]
    y_ramp = np.linspace(0.0, 1.0, height, dtype="float32")[:, None]
    lst = 30.0 + 10.0 * x_ramp + 0.0 * y_ramp + year_offset
    ndvi = 0.6 - 0.4 * y_ramp + 0.0 * x_ramp
    profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1, "dtype": "float32",
        "crs": CRS, "transform": from_origin(west, north, 10, 10), "nodata": -9999.0,
    }
    proc_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("lst_celsius.tif", lst), ("ndvi.tif", ndvi)):
        with rasterio.open(proc_dir / name, "w", **profile) as dst:
            dst.write(data.astype("float32"), 1)


@pytest.fixture
def city_workspace(monkeypatch, tmp_path):
    raw_root, proc_root = tmp_path / "raw", tmp_path / "proc"
    monkeypatch.setattr(ia, "city_data_raw", lambda city_id: raw_root / city_id)
    monkeypatch.setattr(ia, "city_data_proc", lambda city_id: proc_root / city_id)
    monkeypatch.setattr(
        ia, "year_paths",
        lambda city_id, year, main: (
            (raw_root / city_id, proc_root / city_id) if year == main
            else (raw_root / city_id / year, proc_root / city_id / year)
        ),
    )
    main_year = YEARS[-1]
    for offset, year in enumerate(YEARS):
        raw_dir, proc_dir = ia.year_paths("testcity", year, main_year)
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "scene_metadata.json").write_text(
            json.dumps({"scenes": [{"date": f"{year}-07-15"}]}), encoding="utf-8",
        )
        _write_rasters(proc_dir, year_offset=float(offset))

    lines, districts = [], []
    for i in range(12):
        lon = BBOX[0] + 0.002 + i * 0.0021
        lat = BBOX[1] + 0.002 + (i % 4) * 0.004
        lines.append(LineString([(lon, lat), (lon + 0.002, lat + 0.001)]))
        districts.append("Kuzey" if i < 6 else "Güney")
    roads = gpd.GeoDataFrame({
        "name": [f"Yol {i}" for i in range(12)],
        "mahalle_adi": ["M"] * 12,
        "ilce_adi": districts,
        "nufus_yogunlugu": np.linspace(100, 900, 12),
        "yasli_oran": [0.05] * 6 + [0.15] * 6,
        "cocuk_oran": [0.2] * 12,
        "length": [200.0] * 12,
        "exposure_norm": np.linspace(0, 1, 12),
        "sensitivity_yasli_norm": [0.0] * 6 + [1.0] * 6,
        "sensitivity_cocuk_norm": [0.5] * 12,
        "sensitivity_saglik_norm": np.linspace(1, 0, 12),
        "sensitivity_yesil_norm": np.linspace(0.2, 0.8, 12),
        "sensitivity_yapilasma_norm": np.linspace(0.3, 0.7, 12),
        "geometry": lines,
    }, crs="EPSG:4326")
    to_utm_roads = roads.to_crs(CRS)
    for offset, year in enumerate(YEARS):
        centers = to_utm_roads.geometry.centroid.to_crs("EPSG:4326")
        roads[f"lst_mean_{year}"] = 30.0 + 10.0 * (centers.x - (BBOX[0] - 0.005)) / (BBOX[2] - BBOX[0] + 0.01) + offset
        roads[f"ndvi_mean_{year}"] = 0.4
    proc_dir = proc_root / "testcity"
    proc_dir.mkdir(parents=True, exist_ok=True)
    roads.to_file(proc_dir / "roads_with_hvi.geojson", driver="GeoJSON")

    grid = ia._weather_grid(_make_config())
    days = pd.date_range("1991-06-24", "2024-09-07", freq="D")

    def location():
        temps = np.full(len(days), 25.0)
        for offset, year in enumerate(YEARS):
            temps[list(days).index(pd.Timestamp(f"{year}-07-15"))] += 2.0 * (offset + 1)
        return {"daily": {"time": [d.strftime("%Y-%m-%d") for d in days], "temperature_2m_mean": temps.tolist()}}

    locations = [location() for _ in grid]
    monkeypatch.setattr(ia, "_load_weather", lambda cfg, years: (locations, grid))
    return proc_dir


def test_run_impact_analysis_writes_consistent_package(city_workspace):
    output_dir = ia.run_impact_analysis(_make_config(), YEARS, YEARS[-1], buffers_m=[10, 30])

    summary = json.loads((output_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    assert summary["years"] == [2020, 2022, 2024]
    assert summary["weather_beta"] == 1.0
    for name in summary["outputs"]:
        assert (output_dir / name).exists(), name

    annual = pd.read_csv(output_dir / "annual_weather_adjusted.csv")
    # 2020 sahne günü taban döneme (1991-2020) girdiği için normali çok az yükseltir.
    assert annual["mean_era5_air_temp_anomaly_c"].tolist() == pytest.approx([2.0, 4.0, 6.0], abs=0.01)
    # β=1: hava anomalisi LST'den birebir çıkarılır; β=0 ham LST'dir.
    assert np.allclose(
        annual["mean_lst_c"] - annual["mean_era5_air_temp_anomaly_c"],
        annual["mean_weather_adjusted_lst_c"], atol=1e-3,
    )
    assert np.allclose(annual["beta_0_mean_lst_c"], annual["mean_lst_c"])
    # Rasterlar yıl başına +1 °C ısınıyor, hava ise +2 °C: düzeltilmiş eğilim ham eğilimden düşük.
    assert summary["raw_lst_linear_trend_c_per_year"] == pytest.approx(0.5, abs=0.05)
    assert summary["weather_adjusted_lst_linear_trend_c_per_year"] < summary["raw_lst_linear_trend_c_per_year"]

    robustness = pd.read_csv(output_dir / "robustness.csv")
    baseline = robustness[(robustness["buffer_m"] == 10) & (robustness["weight_profile"] == "equal")]
    assert baseline["spearman_rank_correlation"].iloc[0] == 1.0

    validation = summary["validation"]
    assert validation["available"] is True
    assert {row["district_count"] for row in validation["correlations"]} == {2}

    impact = gpd.read_file(output_dir / "impact_scenarios.geojson")
    assert impact["targeted_for_scenario"].sum() == 3  # 12 yolun %20'si, yukarı yuvarlanır


@pytest.mark.parametrize("kwargs, message", [
    ({"years": ["2020", "2022"]}, "en az üç"),
    ({"target_share": 0}, "target_share"),
    ({"target_share": 1.5}, "target_share"),
    ({"cooling_c": -1}, "negatif"),
    ({"weather_beta": -0.1}, "weather_beta"),
    ({"buffers_m": [10, -5]}, "pozitif"),
])
def test_run_impact_analysis_rejects_invalid_arguments(kwargs, message):
    arguments = {"years": YEARS}
    arguments.update(kwargs)
    years = arguments.pop("years")
    with pytest.raises(ValueError, match=message):
        ia.run_impact_analysis(_make_config(), years, years[-1], **arguments)


def test_run_impact_analysis_requires_pipeline_output(monkeypatch, tmp_path):
    monkeypatch.setattr(ia, "city_data_proc", lambda city_id: tmp_path / "yok")
    with pytest.raises(FileNotFoundError, match="pipeline.py"):
        ia.run_impact_analysis(_make_config(), YEARS, YEARS[-1])
