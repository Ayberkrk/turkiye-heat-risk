import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

import core.hvi as hvi
from core.city_config import CityConfig
from core.hvi import (
    COMPONENT_FLOOR, bucket_5, combine_groups, group_scores, hvi_from_components,
    informative_components, normalize_0_1, pooled_group_bounds, rescale_groups, robust_bounds,
    robust_normalize_0_1,
)


def test_normalize_0_1_maps_min_max_to_0_1():
    result = normalize_0_1(pd.Series([10, 20, 30]))
    assert result.tolist() == [0.0, 0.5, 1.0]


def test_normalize_0_1_constant_series_returns_all_zero():
    # min == max olduğunda (ör. şehrin tamamı aynı sosyoekonomik ilçede)
    # bölme sıfıra düşer - fonksiyon bunun yerine sabit 0 döndürmeli.
    result = normalize_0_1(pd.Series([5, 5, 5]))
    assert (result == 0).all()


def test_normalize_0_1_preserves_index():
    # HVI birleştirme sırasında sonuç orijinal (boşluklu olabilen) yol
    # indeksine geri hizalanıyor - index kayması sessiz bir hataya yol açar.
    s = pd.Series([1, 2, 3], index=[10, 20, 30])
    result = normalize_0_1(s)
    assert result.index.tolist() == [10, 20, 30]


def test_bucket_5_produces_five_labels_for_skewed_data():
    # Çarpık dağılım: 18 yakın değerin yanında iki uç değer. Eşit
    # genişlikte aralıklar bu durumda tüm satırları tek bir etikette
    # toplardı (bkz. bucket_5 docstring'i); yüzdelik dilim tabanlı bölme,
    # değerler birbirinden ayırt edilebildiği sürece (tekrarsız) her zaman
    # 5 etiketin de kullanılmasını garanti etmeli.
    values = pd.Series(list(range(1, 19)) + [1000, 2000])
    labels = ["çok düşük", "düşük", "orta", "yüksek", "çok yüksek"]
    result = bucket_5(values, labels)
    assert set(result.dropna().unique()) == set(labels)


def test_bucket_5_ties_get_average_rank():
    # Aynı değere sahip çok sayıda satır olsa bile (ör. hiç sağlık
    # noktası olmayan bir bölgede tekrar eden mesafe değerleri) fonksiyon
    # patlamamalı ve hâlâ tanımlı etiketler üretmeli.
    values = pd.Series([0, 0, 0, 0, 0])
    labels = ["a", "b", "c", "d", "e"]
    result = bucket_5(values, labels)
    assert result.notna().all()


# --- Sağlam ölçekleme ------------------------------------------------------

def test_robust_normalize_is_not_compressed_by_a_single_outlier():
    # 99 yol 0-98 m, tek bir yol 100 km uzakta. Min-max'ta medyan yol ~0.0005
    # alır (tüm ölçek uç değere gider); sağlam ölçeklemede ortada kalmalı.
    values = pd.Series(list(range(99)) + [100_000])
    assert normalize_0_1(values).iloc[49] < 0.01
    robust = robust_normalize_0_1(values)
    assert 0.4 < robust.iloc[49] < 0.6
    assert robust.max() == 1.0 and robust.min() == 0.0


def test_robust_bounds_fall_back_to_min_max_when_quantiles_coincide():
    # Yolların %97'si aynı ilçede: %2 ve %98 yüzdelikleri aynı değere düşer.
    # Sınırlar çakışık kalsaydı gerçekte değişen bileşen tümüyle 0 olurdu.
    values = pd.Series([0.10] * 97 + [0.30] * 3)
    assert robust_bounds(values) == (0.10, 0.30)
    assert robust_normalize_0_1(values).iloc[-1] == 1.0


def test_robust_normalize_keeps_nan_and_index():
    result = robust_normalize_0_1(pd.Series([1.0, np.nan, 3.0], index=[10, 20, 30]))
    assert result.index.tolist() == [10, 20, 30]
    assert np.isnan(result.loc[20])


def test_informative_components_drops_constant_columns():
    values = pd.DataFrame({"a": [0.0, 0.0, 0.0], "b": [0.1, 0.2, 0.2], "c": [np.nan, 0.5, 0.5]})
    assert informative_components(values, ["a", "b", "c"]) == ["b"]


# --- Gruplu birleştirme ----------------------------------------------------

# Grup skorlarını olduğu gibi bırakan sınırlar: tek satırlık tablolarda
# birleştirme mantığını yeniden ölçeklemeden bağımsız sınamak için.
UNIT_BOUNDS = {"hazard": (0.0, 1.0), "exposure": (0.0, 1.0), "vulnerability": (0.0, 1.0)}


def _components(**overrides) -> pd.DataFrame:
    base = {
        "hazard_norm": 0.5, "exposure_norm": 0.5, "sensitivity_yapilasma_norm": 0.5,
        "sensitivity_yasli_norm": 0.5, "sensitivity_cocuk_norm": 0.5,
        "sensitivity_sosyoekonomik_norm": 0.5, "sensitivity_saglik_norm": 0.5,
        "sensitivity_yesil_norm": 0.5, "sensitivity_agac_norm": 0.5,
    }
    return pd.DataFrame([{**base, **overrides}])


def test_group_scores_are_member_means():
    groups = group_scores(_components(exposure_norm=0.2, sensitivity_yapilasma_norm=0.6, hazard_norm=0.9))
    assert groups.columns.tolist() == ["hazard", "exposure", "vulnerability"]
    assert np.isclose(groups["hazard"].iloc[0], 0.9)
    assert np.isclose(groups["exposure"].iloc[0], 0.4)
    assert np.isclose(groups["vulnerability"].iloc[0], 0.5)


def test_combine_groups_is_floored_geometric_mean():
    groups = pd.DataFrame({"hazard": [1.0], "exposure": [0.0], "vulnerability": [0.5]})
    floored = COMPONENT_FLOOR + (1 - COMPONENT_FLOOR) * np.array([1.0, 0.0, 0.5])
    assert np.isclose(combine_groups(groups).iloc[0], np.exp(np.log(floored).mean()) * 100)


def test_hazard_weighs_as_much_as_a_whole_group_not_one_of_nine():
    # Tasarımın özü: tehlike tek bileşen olsa da endeksin üçte biridir.
    # Sıcaklığı 0.5 -> 1.0 yapmak, altı kırılganlık bileşeninden yalnızca
    # birini 0.5 -> 1.0 yapmaktan belirgin biçimde daha çok artırmalı; düz
    # dokuz bileşenli geometrik ortalamada ikisi aynı artışı verirdi.
    base = hvi_from_components(_components(), bounds=UNIT_BOUNDS).iloc[0]
    hotter = hvi_from_components(_components(hazard_norm=1.0), bounds=UNIT_BOUNDS).iloc[0]
    older = hvi_from_components(_components(sensitivity_yasli_norm=1.0), bounds=UNIT_BOUNDS).iloc[0]
    assert hotter - base > 3 * (older - base) > 0


def test_group_with_missing_member_is_nan():
    values = _components()
    values.loc[0, "sensitivity_yesil_norm"] = np.nan
    assert np.isnan(hvi_from_components(values, bounds=UNIT_BOUNDS).iloc[0])


def test_component_weights_shift_group_weight():
    # Duyarlılık profili: tehlike ağırlığı 2 ise tehlike grubunun payı artar.
    values = _components(hazard_norm=1.0)
    heavier = hvi_from_components(values, {"hazard_norm": 2.0}, bounds=UNIT_BOUNDS).iloc[0]
    assert heavier > hvi_from_components(values, bounds=UNIT_BOUNDS).iloc[0]


def test_narrow_group_still_moves_the_ranking_after_rescaling():
    # İzmir'de görülen durum: kırılganlık grubu, bileşenleri birbirini
    # götürdüğü için dar bir bantta (burada 0.45-0.55) kalıyor; tehlike ve
    # maruziyet ise tüm aralığa yayılıyor. Yeniden ölçekleme olmadan dar grup
    # sıralamaya neredeyse hiç katkı vermiyordu.
    rng = np.random.default_rng(0)
    n = 2000
    groups = pd.DataFrame({
        "hazard": rng.uniform(0, 1, n), "exposure": rng.uniform(0, 1, n),
        "vulnerability": rng.uniform(0.45, 0.55, n),
    })
    raw = combine_groups(groups)
    bounds = {group: robust_bounds(groups[group]) for group in groups}
    rescaled = combine_groups(rescale_groups(groups, bounds))

    def influence(score):
        return score.rank().corr(groups["vulnerability"].rank())

    assert influence(raw) < 0.15
    assert influence(rescaled) > 0.4


def test_pooled_group_bounds_use_one_ruler_for_all_years():
    # İki yıl ayrı ayrı ölçeklenseydi her yılın en sıcak yolu 1.0 alır ve
    # "ikinci yıl daha sıcak" bilgisi kaybolurdu.
    def table(hazard):
        return pd.DataFrame({"hazard_norm": hazard, "exposure_norm": np.linspace(0, 1, len(hazard))})

    cool, hot = table(np.linspace(0.0, 0.5, 50)), table(np.linspace(0.5, 1.0, 50))
    bounds = pooled_group_bounds([cool, hot])
    assert bounds["hazard"][0] < 0.05 and bounds["hazard"][1] > 0.95
    cool_score = hvi_from_components(cool, bounds=bounds)
    hot_score = hvi_from_components(hot, bounds=bounds)
    assert hot_score.mean() > cool_score.mean()
    # Aynı maruziyetteki yol, sıcak yılda daha yüksek skor almalı.
    assert (hot_score.to_numpy() >= cool_score.to_numpy()).all()


# --- compute_heat_vulnerability_index (uçtan uca, sentetik) ----------------

CRS = "EPSG:32635"
# Jenks'in 5 sınıfı ayırabilmesi için yeterli sayıda farklı skor gerekir.
N_ROADS = 40


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="test", name="Test", bbox=[27.0, 38.0, 27.2, 38.2], crs=CRS, max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
    )


def _run_hvi(monkeypatch, tmp_path, mahalle: gpd.GeoDataFrame, road_x: list[float], risk: list[float]):
    roads = gpd.GeoDataFrame(
        {
            "risk_score_2020": risk,
            "ndvi_mean_2020": np.linspace(0.1, 0.5, len(road_x)),
            "geometry": [LineString([(x, 38.10), (x + 0.001, 38.10)]) for x in road_x],
        },
        crs="EPSG:4326",
    )

    class _Adapter:
        @staticmethod
        def fetch_population_data(config):
            return {}

        @staticmethod
        def build_neighborhood_layer(pbf_path, population_paths, config):
            return mahalle

    points = gpd.GeoDataFrame(geometry=[Point(27.0, 38.10)], crs="EPSG:4326")
    monkeypatch.setattr("core.hvi.load_population_adapter", lambda config: _Adapter)
    monkeypatch.setattr("core.hvi.resolve_pbf_path", lambda city_id: tmp_path / "x.osm.pbf")
    monkeypatch.setattr("core.hvi.city_data_proc", lambda city_id: tmp_path)
    monkeypatch.setattr("core.hvi.load_health_points", lambda config, pbf: points)
    monkeypatch.setattr("core.hvi.load_green_space_polygons",
                        lambda config, pbf: gpd.GeoDataFrame(geometry=[box(27.19, 38.09, 27.2, 38.11)], crs="EPSG:4326"))
    # Yol başına 1-4 bina: yapılaşma yoğunluğu yollar arasında değişsin.
    buildings = [Point(x + 0.0002 * k, 38.1002) for i, x in enumerate(road_x) for k in range(i % 4 + 1)]
    monkeypatch.setattr("core.hvi.load_building_centroids",
                        lambda config, pbf: gpd.GeoDataFrame(geometry=buildings, crs="EPSG:4326"))
    return hvi.compute_heat_vulnerability_index(_make_config(), ["2020"], roads)


def _mahalle(rows: list[dict]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def test_single_district_city_still_gets_a_spread_of_scores(monkeypatch, tmp_path):
    # Tek ilçe: nüfus yoğunluğu, yaşlı ve çocuk oranı tüm yollarda sabit.
    # Bu bileşenler endeksten düşmeli ama skor üretilmeli ve sıcaklıkla artmalı.
    mahalle = _mahalle([{
        "mahalle_adi": "A", "ilce_adi": "Merkez", "nufus_yogunlugu": 5000.0,
        "yasli_oran": 0.10, "cocuk_oran": 0.20, "geometry": box(27.0, 38.0, 27.15, 38.2),
    }])
    road_x = [27.01 + 0.003 * i for i in range(N_ROADS)]
    out = _run_hvi(monkeypatch, tmp_path, mahalle, road_x, risk=list(np.linspace(5, 95, N_ROADS)))

    assert (out["exposure_norm"] == 0).all()
    assert out["hvi_score_2020"].notna().all()
    assert out["hvi_score_2020"].nunique() > 5
    assert out["hvi_score_2020"].iloc[-1] > out["hvi_score_2020"].iloc[0]
    assert {"group_hazard_2020", "group_exposure_2020", "group_vulnerability_2020"} <= set(out.columns)


def test_road_without_demographics_stays_nan_even_when_demographics_are_constant(monkeypatch, tmp_path):
    # Son yol mahalle poligonunun dışında. Demografi sabit olduğu için endekse
    # girmiyor olsa bile, eşlenmemiş yol skor almamalı (kapsam ölçümü buna dayanır).
    mahalle = _mahalle([{
        "mahalle_adi": "A", "ilce_adi": "Merkez", "nufus_yogunlugu": 5000.0,
        "yasli_oran": 0.10, "cocuk_oran": 0.20, "geometry": box(27.0, 38.0, 27.1262, 38.2),
    }])
    road_x = [27.01 + 0.003 * i for i in range(N_ROADS)]
    out = _run_hvi(monkeypatch, tmp_path, mahalle, road_x, risk=list(np.linspace(5, 95, N_ROADS)))

    assert out["hvi_score_2020"].notna().tolist() == [True] * (N_ROADS - 1) + [False]
    assert pd.isna(out["group_vulnerability_2020"].iloc[-1])
