import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

import core.uncertainty as unc
from core.city_config import CityConfig
from core.hvi import (
    combine_groups,
    group_scores,
    pooled_group_bounds,
    rescale_groups,
    robust_bounds,
    robust_normalize_0_1,
    scale_between,
)

YEARS = ["2020", "2026"]
N = 300


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.0, 27.2, 38.2], crs="EPSG:32635", max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
    )


def _roads(seed: int = 0, n: int = N) -> gpd.GeoDataFrame:
    """Ana endeksin (core/hvi.py) adımlarıyla skorlanmış sentetik yol tablosu."""
    rng = np.random.default_rng(seed)
    roads = pd.DataFrame({
        "mahalle_adi": [f"M{i % 6}" for i in range(n)],
        "ilce_adi": ["I"] * n,
        "nufus_yogunlugu": rng.lognormal(8, 1, n),
        "bina_yogunlugu": rng.lognormal(6, 0.5, n),
        "yasli_oran": rng.uniform(0.08, 0.2, n),
        "cocuk_oran": rng.uniform(0.12, 0.3, n),
        "sosyoekonomik_skor": rng.normal(0, 1, n),
        "dist_saglik_m": rng.exponential(500, n),
        "dist_yesil_m": rng.exponential(300, n),
    })
    for k, year in enumerate(YEARS):
        roads[f"risk_score_{year}"] = rng.uniform(0, 100, n) + 5 * k
        roads[f"ndvi_mean_{year}"] = rng.uniform(0.05, 0.6, n)

    roads["exposure_norm"] = robust_normalize_0_1(roads["nufus_yogunlugu"])
    roads["sensitivity_yapilasma_norm"] = robust_normalize_0_1(roads["bina_yogunlugu"])
    roads["sensitivity_yasli_norm"] = robust_normalize_0_1(roads["yasli_oran"])
    roads["sensitivity_cocuk_norm"] = robust_normalize_0_1(roads["cocuk_oran"])
    roads["sensitivity_sosyoekonomik_norm"] = 1 - robust_normalize_0_1(roads["sosyoekonomik_skor"])
    roads["sensitivity_saglik_norm"] = robust_normalize_0_1(roads["dist_saglik_m"])
    roads["sensitivity_yesil_norm"] = robust_normalize_0_1(roads["dist_yesil_m"])
    risk_b = robust_bounds(pd.concat([roads[f"risk_score_{y}"] for y in YEARS]))
    ndvi_b = robust_bounds(pd.concat([roads[f"ndvi_mean_{y}"] for y in YEARS]))
    static = ["exposure_norm", "sensitivity_yapilasma_norm", "sensitivity_yasli_norm", "sensitivity_cocuk_norm",
              "sensitivity_sosyoekonomik_norm", "sensitivity_saglik_norm", "sensitivity_yesil_norm"]
    tables = {}
    for year in YEARS:
        roads[f"hazard_norm_{year}"] = scale_between(roads[f"risk_score_{year}"], *risk_b)
        roads[f"sensitivity_agac_norm_{year}"] = 1 - scale_between(roads[f"ndvi_mean_{year}"], *ndvi_b)
        values = roads[static].copy()
        values["hazard_norm"] = roads[f"hazard_norm_{year}"]
        values["sensitivity_agac_norm"] = roads[f"sensitivity_agac_norm_{year}"]
        tables[year] = values
    bounds = pooled_group_bounds(list(tables.values()))
    for year in YEARS:
        roads[f"hvi_score_{year}"] = combine_groups(rescale_groups(group_scores(tables[year]), bounds))
    geometry = [LineString([(27 + i * 1e-4, 38.1), (27 + i * 1e-4 + 5e-5, 38.1)]) for i in range(n)]
    return gpd.GeoDataFrame(roads, geometry=geometry, crs="EPSG:4326")


def test_default_run_reproduces_the_published_index():
    result = unc.run_uncertainty(_roads(), YEARS, "2026", unc.UncertaintySettings(runs=5))
    assert result["summary"]["default_run_reproduces_published_index_pearson"] == pytest.approx(1.0, abs=1e-9)
    published = _roads()["hvi_score_2026"].rank(pct=True).to_numpy()
    assert result["roads"]["sira_varsayilan"].to_numpy() == pytest.approx(published, abs=1e-6)


def test_same_seed_same_result_different_seed_different_result():
    roads = _roads()
    a = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=30, seed=1))
    b = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=30, seed=1))
    c = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=30, seed=2))
    pd.testing.assert_frame_equal(a["roads"], b["roads"])
    assert not a["roads"]["sira_medyan"].equals(c["roads"]["sira_medyan"])


def test_sampled_decisions_respect_their_constraints():
    cube = unc._ComponentCube(_roads(), YEARS)
    draws = unc.sample_settings(cube, unc.UncertaintySettings(exclusion_probability=1.0), np.random.default_rng(0), 200)

    assert draws[0]["normalization"] == "robust" and draws[0]["aggregation"] == "geometric"
    assert draws[0]["excluded"] is None
    for draw in draws[1:]:
        assert sum(draw["group_weights"].values()) == pytest.approx(1.0)
        # Tek üyeli tehlike grubu asla çıkarılmaz; çıkarılabilir başka bileşen var.
        assert draw["excluded"] not in (None, "hazard_norm")
        assert 0.01 <= draw["floor"] <= 0.10
    assert {d["normalization"] for d in draws[1:]} == set(unc.NORMALIZATIONS)
    assert {d["aggregation"] for d in draws[1:]} == set(unc.AGGREGATIONS)


def test_group_weights_concentrate_around_equal_shares():
    cube = unc._ComponentCube(_roads(), YEARS)
    draws = unc.sample_settings(cube, unc.UncertaintySettings(), np.random.default_rng(0), 2000)
    hazard = np.array([d["group_weights"]["hazard"] for d in draws[1:]])
    assert hazard.mean() == pytest.approx(1 / 3, abs=0.01)
    assert 0.15 < np.quantile(hazard, 0.05) < 0.25 and 0.42 < np.quantile(hazard, 0.95) < 0.52


def test_pooled_scale_uses_one_ruler_for_all_years():
    early, late = np.array([0.0, 10.0]), np.array([10.0, 20.0])
    for method in ("minmax", "rank"):
        scaled_early, scaled_late = unc._pooled_scale([early, late], method)
        # Aynı ham değer (10) iki yılda aynı ölçek değerini almalı.
        assert scaled_early[1] == pytest.approx(scaled_late[0])
        assert scaled_late[1] > scaled_early[0]


def test_dominant_road_is_stably_in_the_top_decile():
    roads = _roads()
    # Her bileşende en riskli değerleri taşıyan yol: hangi karar alınırsa alınsın ilk %10'da.
    i = roads.index[0]
    for year in YEARS:
        roads.loc[i, [f"risk_score_{year}", f"hazard_norm_{year}"]] = [roads[f"risk_score_{year}"].max(), 1.0]
        roads.loc[i, [f"ndvi_mean_{year}", f"sensitivity_agac_norm_{year}"]] = [roads[f"ndvi_mean_{year}"].min(), 1.0]
    for raw, norm in [("nufus_yogunlugu", "exposure_norm"), ("bina_yogunlugu", "sensitivity_yapilasma_norm"),
                      ("yasli_oran", "sensitivity_yasli_norm"), ("cocuk_oran", "sensitivity_cocuk_norm"),
                      ("dist_saglik_m", "sensitivity_saglik_norm"), ("dist_yesil_m", "sensitivity_yesil_norm")]:
        roads.loc[i, [raw, norm]] = [roads[raw].max(), 1.0]
    roads.loc[i, ["sosyoekonomik_skor", "sensitivity_sosyoekonomik_norm"]] = [roads["sosyoekonomik_skor"].min(), 1.0]
    roads[[f"hvi_score_{y}" for y in YEARS]] = roads[[f"hvi_score_{y}" for y in YEARS]].fillna(0)

    result = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=60))
    assert result["roads"].loc[i, "olasilik_ilk_yuzde10"] == 1.0
    assert result["roads"].loc[i, "sira_p05"] > 0.9


def test_roads_without_a_score_are_left_out():
    roads = _roads()
    roads.loc[roads.index[:7], "hvi_score_2020"] = np.nan
    result = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=5))
    assert len(result["roads"]) == N - 7
    assert not set(roads.index[:7]) & set(result["roads"].index)


def test_constant_component_is_not_part_of_the_cube():
    roads = _roads()
    roads["yasli_oran"] = 0.1
    roads["sensitivity_yasli_norm"] = 0.0
    cube = unc._ComponentCube(roads, YEARS)
    assert "sensitivity_yasli_norm" not in cube.components
    assert "hazard_norm" in cube.components


def test_first_order_index_finds_the_factor_that_drives_the_output():
    rng = np.random.default_rng(0)
    factors = pd.DataFrame({
        "etkili": rng.uniform(0, 1, 2000),
        "gurultu": rng.uniform(0, 1, 2000),
        "kategori": rng.choice(["a", "b"], 2000).astype(object),
    })
    outputs = pd.DataFrame({"y": 3 * factors["etkili"] + rng.normal(0, 0.1, 2000)})
    s = unc.first_order_indices(factors, outputs)["y"]
    assert s["etkili"] > 0.9
    assert s["gurultu"] < 0.02 and s["kategori"] < 0.02


def test_mahalle_ranks_and_outputs_are_written(tmp_path):
    roads = _roads()
    result = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=20))
    mahalle = result["mahalle"]
    assert len(mahalle) == 6  # her mahallede 50 yol, hepsi eşiği geçer
    assert (mahalle["sira_p05"] <= mahalle["sira_medyan"]).all()
    assert (mahalle["sira_medyan"] <= mahalle["sira_p95"]).all()

    out = unc.write_uncertainty_outputs(_make_config(), roads, result, output_dir=tmp_path)
    names = {p.name for p in out.iterdir()}
    assert {"belirsizlik_yollar.geojson", "belirsizlik_mahalleler.csv", "belirsizlik_duyarlilik.csv",
            "belirsizlik_kosular.csv", "belirsizlik_ozet.json"} <= names
    summary = json.loads((out / "belirsizlik_ozet.json").read_text(encoding="utf-8"))
    assert summary["road_count"] == N and summary["settings"]["runs"] == 20
    written = gpd.read_file(out / "belirsizlik_yollar.geojson")
    assert len(written) == N and {"olasilik_ilk_yuzde10", "sira_bandi"} <= set(written.columns)


def test_too_few_runs_is_an_error():
    with pytest.raises(ValueError, match="iki koşu"):
        unc.run_uncertainty(_roads(), YEARS, "2026", unc.UncertaintySettings(runs=1))


def test_single_member_group_weight_is_not_reported_as_a_decision():
    roads = _roads()
    result = unc.run_uncertainty(roads, YEARS, "2026", unc.UncertaintySettings(runs=40))
    assert "bilesen_agirligi:hazard_norm" not in result["runs"].columns
    assert "bilesen_agirligi:hazard_norm" not in result["sensitivity"].index
