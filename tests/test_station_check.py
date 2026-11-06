import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

import core.station_check as sc
from core.city_config import CityConfig
from core.raster import QA_BIT_CLOUD

GHCNH_HEADER = "STATION|DATE|temperature|temperature_Quality_Code|dew_point_temperature"


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.3, 27.2, 38.5], crs="EPSG:32635", max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
    )


def test_parse_ghcnh_drops_failed_quality_flags_and_keeps_utc_times():
    text = "\n".join([
        GHCNH_HEADER,
        "X|2026-07-01T08:00:00|31.0|1|10",
        "X|2026-07-01T08:20:00|99.0|L|10",   # harf: başarısız kalite testi
        "X|2026-07-01T08:50:00|32.5||10",
        "X|2026-07-01T09:00:00||1|10",       # sıcaklık yok
    ])
    frame = sc.parse_ghcnh(text)
    assert frame["air_temp_c"].tolist() == [31.0, 32.5]
    assert str(frame["time"].dt.tz) == "UTC"


def test_nearest_observation_respects_the_time_gap():
    obs = pd.DataFrame({"time": pd.to_datetime(["2026-07-01T08:00:00Z", "2026-07-01T10:00:00Z"]),
                        "air_temp_c": [30.0, 34.0]})
    assert sc.nearest_observation(obs, datetime(2026, 7, 1, 8, 30, tzinfo=UTC)) == 30.0
    # 08:40 ile hem 08:00 hem 10:00 arasında 40 dakikadan fazla var mı? 08:00 40 dk: kabul.
    assert sc.nearest_observation(obs, datetime(2026, 7, 1, 8, 40, tzinfo=UTC)) == 30.0
    assert sc.nearest_observation(obs, datetime(2026, 7, 1, 9, 0, tzinfo=UTC)) is None
    assert sc.nearest_observation(obs.iloc[0:0], datetime(2026, 7, 1, 8, 0, tzinfo=UTC)) is None


def _write_scene(folder, thermal_dn, qa):
    folder.mkdir(parents=True, exist_ok=True)
    transform = from_origin(500000, 4250000, 30, 30)  # UTM 35N, ~38.4 K, 27.0 D civarı
    common = {"driver": "GTiff", "height": thermal_dn.shape[0], "width": thermal_dn.shape[1], "count": 1,
              "crs": "EPSG:32635", "transform": transform}
    with rasterio.open(folder / "band10_thermal.tif", "w", dtype="uint16", nodata=0, **common) as dst:
        dst.write(thermal_dn.astype("uint16"), 1)
    with rasterio.open(folder / "band_qa_pixel.tif", "w", dtype="uint16", **common) as dst:
        dst.write(qa.astype("uint16"), 1)
    return transform


def _dn_for(celsius: float) -> int:
    return round((celsius + 273.15 - 149.0) / 0.00341802)


def _center_lonlat(transform, row, col):
    from rasterio.warp import transform as warp

    x, y = rasterio.transform.xy(transform, row, col)
    lon, lat = warp("EPSG:32635", "EPSG:4326", [x], [y])
    return lon[0], lat[0]


def test_lst_at_point_uses_median_of_clear_pixels(tmp_path):
    dn = np.full((20, 20), _dn_for(40.0))
    dn[10, 10] = _dn_for(80.0)        # tek sıcak piksel medyanı bozmamalı
    qa = np.zeros((20, 20))
    qa[9, 9] = 1 << QA_BIT_CLOUD
    transform = _write_scene(tmp_path / "s", dn, qa)
    lon, lat = _center_lonlat(transform, 10, 10)

    lst, n = sc.lst_at_point(tmp_path / "s" / "band10_thermal.tif", tmp_path / "s" / "band_qa_pixel.tif", lon, lat)
    assert n == 8  # 9 pikselden biri bulutlu
    assert lst == pytest.approx(40.0, abs=0.01)


def test_lst_at_point_refuses_mostly_cloudy_or_edge_points(tmp_path):
    dn = np.full((20, 20), _dn_for(40.0))
    qa = np.zeros((20, 20))
    qa[8:12, 8:12] = 1 << QA_BIT_CLOUD
    transform = _write_scene(tmp_path / "s", dn, qa)
    lon, lat = _center_lonlat(transform, 10, 10)
    assert sc.lst_at_point(tmp_path / "s" / "band10_thermal.tif", tmp_path / "s" / "band_qa_pixel.tif", lon, lat)[0] is None
    edge_lon, edge_lat = _center_lonlat(transform, 0, 0)
    assert sc.lst_at_point(tmp_path / "s" / "band10_thermal.tif", tmp_path / "s" / "band_qa_pixel.tif",
                           edge_lon, edge_lat) == (None, 0)


def test_stations_in_bbox():
    stations = pd.DataFrame({"id": ["A", "B"], "lat": [38.4, 39.5], "lon": [27.1, 27.1], "name": ["İç", "Dış"]})
    assert sc.stations_in_bbox(stations, [27.0, 38.3, 27.2, 38.5])["id"].tolist() == ["A"]


def test_compare_scenes_pairs_each_scene_with_the_overpass_observation(monkeypatch, tmp_path):
    dn = np.full((20, 20), _dn_for(45.0))
    transform = _write_scene(tmp_path / "2026" / "SCENE_A", dn, np.zeros((20, 20)))
    lon, lat = _center_lonlat(transform, 10, 10)
    (tmp_path / "2026" / "scene_metadata.json").write_text(json.dumps({"scenes": [
        {"scene_id": "SCENE_A", "folder": "SCENE_A", "date": "2026-07-10"}]}), encoding="utf-8")
    monkeypatch.setattr("core.station_check.year_paths", lambda city, year, main: (tmp_path / year, tmp_path))
    obs = pd.DataFrame({"time": pd.to_datetime(["2026-07-10T08:50:00Z"]), "air_temp_c": [31.0]})
    monkeypatch.setattr("core.station_check.load_station_year", lambda config, sid, year: obs)
    stations = pd.DataFrame({"id": ["ST"], "name": ["İstasyon"], "lat": [lat], "lon": [lon]})

    table = sc.compare_scenes(_make_config(), ["2026"], "2026", stations)
    assert len(table) == 1
    row = table.iloc[0]
    assert row["lst_c"] == pytest.approx(45.0, abs=0.01)
    assert row["hava_sicakligi_c"] == 31.0 and row["fark_c"] == pytest.approx(14.0, abs=0.01)


def test_summary_reports_offsets_temporal_agreement_and_year_change():
    rng = np.random.default_rng(0)
    rows = []
    for station, offset in (("A", 12.0), ("B", 16.0)):
        for year, shift in (("2020", 0.0), ("2026", 1.0)):
            for day in range(6):
                air = 30 + rng.normal(0, 2) + shift
                rows.append({"yil": year, "tarih": f"{year}-07-{day + 1:02d}", "istasyon": station,
                             "istasyon_adi": station, "lst_c": air + offset + rng.normal(0, 0.3),
                             "hava_sicakligi_c": air})
    table = pd.DataFrame(rows)
    table["fark_c"] = table["lst_c"] - table["hava_sicakligi_c"]
    summary = sc.summarize(table, ["2020", "2026"])
    offsets = {s["istasyon"]: s["ort_fark_c"] for s in summary["stations"]}
    assert offsets["A"] == pytest.approx(12.0, abs=0.3) and offsets["B"] == pytest.approx(16.0, abs=0.3)
    # İstasyonlar arası sabit fark ayıklanınca LST hava sıcaklığını yakından izler.
    assert summary["pearson_within_station_anomalies"] > 0.9
    changes = {c["istasyon"]: c for c in summary["year_change"]}
    assert changes["A"]["hava_degisim_c"] == pytest.approx(changes["A"]["lst_degisim_c"], abs=0.5)
    assert sc.summarize(table.iloc[0:0], ["2020"]) == {"pairs": 0}
