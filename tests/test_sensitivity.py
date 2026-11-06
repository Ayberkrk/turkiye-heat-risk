import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString
from test_uncertainty import YEARS, _roads

import core.sensitivity as sens
from core.city_config import CityConfig


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.0, 27.2, 38.2], crs="EPSG:32635", max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
    )


def test_shapley_parts_add_up_to_the_total_change():
    roads = _roads()
    result = sens.temporal_decomposition(roads, YEARS)
    table = result["roads"]
    assert (table["sicaklik_katkisi"] + table["ndvi_katkisi"]).to_numpy() == pytest.approx(
        table["toplam_degisim"].to_numpy(), abs=1e-9)
    # Varsayılan adımlar yayımlanan skoru birebir verir.
    assert result["summary"]["reproduces_published_last_year_pearson"] == pytest.approx(1.0, abs=1e-9)


def test_unchanged_vegetation_contributes_nothing():
    roads = _roads()
    roads["sensitivity_agac_norm_2026"] = roads["sensitivity_agac_norm_2020"]
    table = sens.temporal_decomposition(roads, YEARS)["roads"]
    assert table["ndvi_katkisi"].abs().max() == pytest.approx(0.0, abs=1e-9)
    assert table["sicaklik_katkisi"].to_numpy() == pytest.approx(table["toplam_degisim"].to_numpy())


def test_summary_states_what_was_held_constant_and_not_measured():
    summary = sens.temporal_decomposition(_roads(), YEARS)["summary"]
    assert "SEGE-2022" in summary["held_constant"]
    assert "2020" in summary["not_measured"]
    assert 0 <= summary["share_of_abs_change_from_heat"] <= 1


def _write_raster(path, data, transform):
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype="float32", crs="EPSG:32635", transform=transform, nodata=-9999.0) as dst:
        dst.write(data.astype("float32"), 1)


def test_buffer_sensitivity_detects_roads_next_to_a_cool_strip(monkeypatch, tmp_path):
    # 30 m pikseller; yollar doğu-batı. Yolların bir kısmının 40 m kuzeyinde
    # serin bir şerit var: 10 m tampon onu görmez, 50 m tampon görür.
    transform = from_origin(500000, 4220000, 30, 30)
    rng = np.random.default_rng(1)
    n = 60
    roads = _roads(n=n)
    xs = 500000 + 60 * np.arange(n)
    geoms = [LineString([(x, 4219000), (x + 40, 4219000)]) for x in xs]
    roads = roads.set_geometry(pd.Series(geoms, index=roads.index)).set_crs("EPSG:32635", allow_override=True)
    roads = roads.to_crs("EPSG:4326")
    roads["highway"] = ["primary" if i % 2 else "residential" for i in range(n)]
    for year in YEARS:
        folder = tmp_path / year
        folder.mkdir()
        lst = np.full((100, 150), 40.0) + rng.normal(0, 0.01, (100, 150))
        lst[:, :] += np.linspace(0, 5, 150)  # doğuya doğru ısınan zemin, sıralamayı belirler
        lst[31:33, :75] = 20.0               # batı yarıda, yolların ~45 m kuzeyinde serin şerit
        _write_raster(folder / "lst_celsius.tif", lst, transform)
        _write_raster(folder / "ndvi.tif", np.full((100, 150), 0.3), transform)
    monkeypatch.setattr("core.sensitivity.year_paths", lambda city, year, main: (tmp_path, tmp_path / year))

    result = sens.buffer_sensitivity(_make_config(), roads, YEARS, "2026", (10, 50))
    summary = result["summary"].iloc[0]
    assert summary["tampon_m"] == 50 and summary["spearman"] < 1.0
    change = result["roads"]["sira_degisimi_50m"]
    west = result["roads"].index[:n // 2 - 5]
    east = result["roads"].index[n // 2 + 5:]
    # Serin şeridin yanındaki (batı) yollar geniş tamponda sıra kaybeder.
    assert change.loc[west].mean() < change.loc[east].mean()


def test_write_outputs(tmp_path):
    roads = _roads()
    temporal = sens.temporal_decomposition(roads, YEARS)
    out = sens.write_sensitivity_outputs(_make_config(), roads, None, temporal, output_dir=tmp_path)
    # Sentetik tabloda kategori sütunu yok: geçiş tablosu yazılmaz.
    assert {p.name for p in out.iterdir()} == {"zamansal_ayristirma_yollar.csv", "zamansal_ayristirma_ilce.csv",
                                               "duyarlilik_ozet.json"}
