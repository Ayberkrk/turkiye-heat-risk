import csv
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from core.city_config import CITIES_DIR, CityConfig, load_city_config
from core.ilce_table_adapter import build_neighborhood_layer_from_ilce_tables, resolve_merkez_aliases

CRS = "EPSG:32636"


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="testcity", name="Test City", bbox=[30.5, 36.7, 31.0, 37.0], crs=CRS,
        max_cloud_cover=30, osm_pbf_url="http://example.com/x.pbf", drive_highway_types=["primary"],
        admin_level_ilce="6", admin_level_mahalle="8", population_adapter_path="cities.testcity.adapter",
    )


def _osm_frame(ilce: dict[str, tuple], mahalle: list[tuple]) -> gpd.GeoDataFrame:
    """`ilce`: ad -> (xmin, ymin, xmax, ymax); `mahalle`: (ad, kutu) listesi.

    gpd.read_file'ın OGR "osm" şemasındaki multipolygons katmanını taklit
    eder: admin_level/boundary/name sütunları, EPSG:4326 geometri.
    """
    rows = [(name, "6", "administrative", box(*b)) for name, b in ilce.items()]
    rows += [(name, "8", "administrative", box(*b)) for name, b in mahalle]
    return gpd.GeoDataFrame(
        {"name": [r[0] for r in rows], "admin_level": [r[1] for r in rows],
         "boundary": [r[2] for r in rows], "geometry": [r[3] for r in rows]},
        crs="EPSG:4326",
    )


def _write_tables(tmp_path: Path, nufus_rows: list[tuple], sege_rows: list[tuple]) -> tuple[Path, Path]:
    nufus_csv, sege_csv = tmp_path / "ilce_nufus.csv", tmp_path / "sege.csv"
    nufus_csv.write_text("ILCE;NUFUS;YASLI_ORAN;COCUK_ORAN\n" + "".join(f"{a};{b};{c};{d}\n" for a, b, c, d in nufus_rows))
    sege_csv.write_text("ILCE;SKOR\n" + "".join(f"{a};{b}\n" for a, b in sege_rows))
    return nufus_csv, sege_csv


# Kare ilçeler: A batıda, B doğuda, ikisi de aynı boyutta (aynı alan).
ILCE = {"Muratpaşa": (30.60, 36.80, 30.70, 36.90), "Kepez": (30.70, 36.80, 30.80, 36.90)}


def test_mahalle_gets_values_of_the_ilce_containing_its_centroid(tmp_path, monkeypatch):
    osm = _osm_frame(ILCE, [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84)),
                             ("Iki Mahallesi", (30.72, 36.82, 30.74, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path,
                                [("Muratpaşa", 100000, 0.10, 0.20), ("Kepez", 300000, 0.12, 0.25)],
                                [("Muratpaşa", 3.0), ("Kepez", 1.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege).set_index("mahalle_adi")

    assert result.loc["Bir Mahallesi", "ilce_adi"] == "Muratpaşa"
    assert result.loc["Bir Mahallesi", "yasli_oran"] == 0.10
    assert result.loc["Iki Mahallesi", "cocuk_oran"] == 0.25
    assert result.loc["Bir Mahallesi", "sosyoekonomik_skor"] == 3.0
    assert result.loc["Iki Mahallesi", "sosyoekonomik_skor"] == 1.0


def test_population_density_scales_with_ilce_population(tmp_path, monkeypatch):
    # İki ilçe aynı alanda; nüfusları 1:3 oranında -> yoğunluklar da 1:3
    # olmalı (alanın kendisini yeniden hesaplamadan formülü doğrular).
    osm = _osm_frame(ILCE, [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84)),
                             ("Iki Mahallesi", (30.72, 36.82, 30.74, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path,
                                [("Muratpaşa", 100000, 0.1, 0.2), ("Kepez", 300000, 0.1, 0.2)],
                                [("Muratpaşa", 1.0), ("Kepez", 1.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege).set_index("mahalle_adi")

    ratio = result.loc["Iki Mahallesi", "nufus_yogunlugu"] / result.loc["Bir Mahallesi", "nufus_yogunlugu"]
    assert ratio == pytest.approx(3.0, rel=0.01)


def test_ilce_names_match_across_turkish_casing_between_osm_and_csv(tmp_path, monkeypatch):
    # OSM'de "MURATPAŞA", CSV'de "Muratpaşa" - normalize_name ikisini
    # eşleştirmeli, aksi halde tüm demografi sessizce NaN kalır.
    osm = _osm_frame({"MURATPAŞA": ILCE["Muratpaşa"]}, [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path, [("Muratpaşa", 100000, 0.1, 0.2)], [("Muratpaşa", 2.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege)

    assert result["nufus_yogunlugu"].notna().all()
    assert result["sosyoekonomik_skor"].notna().all()


def test_ilce_missing_from_csv_yields_nan_and_prints_a_warning(tmp_path, monkeypatch, capsys):
    osm = _osm_frame(ILCE, [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84)),
                             ("Iki Mahallesi", (30.72, 36.82, 30.74, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path, [("Muratpaşa", 100000, 0.1, 0.2)], [("Muratpaşa", 2.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege).set_index("mahalle_adi")

    assert result.loc["Bir Mahallesi", "nufus_yogunlugu"] > 0
    assert result.loc["Iki Mahallesi", ["nufus_yogunlugu", "yasli_oran", "cocuk_oran", "sosyoekonomik_skor"]].isna().all()
    warning = capsys.readouterr().out
    assert "UYARI" in warning and "Kepez" in warning


def test_mahalle_outside_every_ilce_is_dropped(tmp_path, monkeypatch):
    osm = _osm_frame({"Muratpaşa": ILCE["Muratpaşa"]},
                     [("Icerde Mahallesi", (30.62, 36.82, 30.64, 36.84)),
                      ("Disarda Mahallesi", (30.90, 36.95, 30.92, 36.97))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path, [("Muratpaşa", 100000, 0.1, 0.2)], [("Muratpaşa", 2.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege)

    assert result["mahalle_adi"].tolist() == ["Icerde Mahallesi"]


def test_same_named_mahalle_in_two_ilce_keeps_each_ilce_values(tmp_path, monkeypatch):
    # "Atatürk Mahallesi" gibi aynı isimli mahalleler çok yaygın; eşleme
    # isme değil konuma göre yapıldığından her biri kendi ilçesinin
    # değerini almalı.
    osm = _osm_frame(ILCE, [("Ataturk Mahallesi", (30.62, 36.82, 30.64, 36.84)),
                             ("Ataturk Mahallesi", (30.72, 36.82, 30.74, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path,
                                [("Muratpaşa", 100000, 0.10, 0.20), ("Kepez", 300000, 0.12, 0.25)],
                                [("Muratpaşa", 3.0), ("Kepez", 1.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege)

    by_ilce = result.set_index("ilce_adi")["sosyoekonomik_skor"].to_dict()
    assert by_ilce == {"Muratpaşa": 3.0, "Kepez": 1.0}


# --- "<Il> Merkez" (OSM) <-> "Merkez" (TUIK/SEGE tablosu) eslemesi -------------
#
# Gercek OSM verisiyle bulunan hata: Burdur/Isparta/Osmaniye/Adiyaman/Siirt/
# Sirnak'ta OSM ilce adi "Burdur Merkez" iken tabloda "Merkez" yaziyordu, hicbir
# mahalle eslesmiyor ve HVI kapsami %0 cikiyordu.

def test_merkez_alias_maps_the_single_il_merkez_candidate():
    assert resolve_merkez_aliases(["BURDUR MERKEZ", "BUCAK"], {"MERKEZ"}) == {"BURDUR MERKEZ": "MERKEZ"}


def test_merkez_alias_is_skipped_when_table_has_no_merkez_row():
    assert resolve_merkez_aliases(["BURDUR MERKEZ"], {"FATIH"}) == {}


def test_merkez_alias_works_in_the_reverse_direction_too():
    # Tabloda "Amasya Merkez", OSM'de yalnızca "Merkez".
    assert resolve_merkez_aliases(["MERKEZ", "TASOVA"], {"AMASYA MERKEZ"}) == {"MERKEZ": "AMASYA MERKEZ"}


def test_merkez_alias_is_skipped_when_two_provinces_merkez_are_present():
    # bbox iki ilin merkez ilcesine tasiyorsa hangisinin tablodaki "Merkez"
    # oldugu bilinemez; yanlis ile eslemektense eslememek dogrudur.
    assert resolve_merkez_aliases(["BURDUR MERKEZ", "ISPARTA MERKEZ"], {"MERKEZ"}) == {}


def test_merkez_alias_ignores_names_that_already_match_the_table():
    assert resolve_merkez_aliases(["MERKEZ"], {"MERKEZ"}) == {}


def test_il_merkez_in_osm_gets_demographics_from_plain_merkez_row(tmp_path, monkeypatch):
    osm = _osm_frame({"Burdur Merkez": ILCE["Muratpaşa"]}, [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path, [("Merkez", 100000, 0.1, 0.2)], [("Merkez", 2.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege)

    assert result["nufus_yogunlugu"].notna().all()
    assert result["sosyoekonomik_skor"].tolist() == [2.0]


def test_two_il_merkez_in_bbox_stay_unmatched_and_warn(tmp_path, monkeypatch, capsys):
    osm = _osm_frame({"Burdur Merkez": ILCE["Muratpaşa"], "Isparta Merkez": ILCE["Kepez"]},
                     [("Bir Mahallesi", (30.62, 36.82, 30.64, 36.84)), ("Iki Mahallesi", (30.72, 36.82, 30.74, 36.84))])
    monkeypatch.setattr("core.ilce_table_adapter.gpd.read_file", lambda *a, **k: osm)
    nufus, sege = _write_tables(tmp_path, [("Merkez", 100000, 0.1, 0.2)], [("Merkez", 2.0)])

    result = build_neighborhood_layer_from_ilce_tables(Path("dummy.pbf"), _make_config(), nufus, sege)

    assert result["nufus_yogunlugu"].isna().all()
    assert "UYARI" in capsys.readouterr().out


# --- Repoyla gelen gerçek şehir verilerinin bütünlüğü -----------------------
#
# Yeni bir TÜİK-şablonlu şehir eklendiğinde CSV yazım hatası, ilçe adı
# uyuşmazlığı ya da oran biriminin (%, 0-1) karışması gibi hataları ağ/OSM
# indirmeden yakalar. İzmir'in nüfus verisi canlı CKAN'dan geldiği için
# (statik ilce_nufus.csv'si yok) bu şablon kapsamı dışındadır.

def _table_cities() -> list[str]:
    return sorted(p.name for p in CITIES_DIR.iterdir() if (p / "ilce_nufus.csv").exists())


def _read_semicolon_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def test_at_least_one_table_city_ships_with_the_repo():
    assert _table_cities(), "src/cities altında ilce_nufus.csv taşıyan şehir bulunamadı"


@pytest.mark.parametrize("city_id", _table_cities())
def test_shipped_city_tables_are_consistent(city_id):
    nufus = _read_semicolon_csv(CITIES_DIR / city_id / "ilce_nufus.csv")
    sege = _read_semicolon_csv(CITIES_DIR / city_id / "sege_2022_ilce.csv")

    nufus_ilce = [row["ILCE"] for row in nufus]
    assert len(nufus_ilce) == len(set(nufus_ilce)), "ilce_nufus.csv'de tekrar eden ilçe var"
    for row in nufus:
        assert int(row["NUFUS"]) > 0
        # Oranlar 0-1 arası kesir olmalı; yüzde (43.3) yazılırsa çok büyük
        # bir bileşen üretir ve tüm HVI sıralamasını bozar.
        assert 0 < float(row["YASLI_ORAN"]) < 1
        assert 0 < float(row["COCUK_ORAN"]) < 1
        assert float(row["YASLI_ORAN"]) + float(row["COCUK_ORAN"]) < 1

    # Her nüfus satırının bir SEGE karşılığı olmalı - yoksa o ilçenin
    # sosyoekonomik bileşeni sessizce NaN kalır.
    assert set(nufus_ilce) <= {row["ILCE"] for row in sege}
    for row in sege:
        assert -3 < float(row["SKOR"]) < 8  # SEGE-2022 skor aralığı (yaklaşık -1,5 ... +6,96)
        assert 1 <= int(row["KADEME"]) <= 6


@pytest.mark.parametrize("city_id", _table_cities())
def test_shipped_city_config_loads_and_points_at_its_own_adapter(city_id):
    config = load_city_config(city_id)
    assert config.population_adapter_path == f"cities.{city_id}.adapter"


def _expected_kademe(skor: float) -> int:
    """SEGE-2022 raporunun kademe sinirlari (rapor, Sonuc ve Degerlendirme): 1.
    kademe >= 1,632; 2. 1,581 ... 0,396; 3. 0,379 ... -0,173; 4. -0,178 ...
    -0,493; 5. -0,500 ... -0,824; 6. <= -0,831. Kademeler arasindaki bosluklarin
    ortasindan kesilir (hicbir ilce bu bosluklara dusmez).
    """
    for esik, kademe in ((1.6, 1), (0.388, 2), (-0.1755, 3), (-0.4965, 4), (-0.8275, 5)):
        if skor >= esik:
            return kademe
    return 6


@pytest.mark.parametrize("city_id", _table_cities())
def test_shipped_city_kademe_matches_sege_score_thresholds(city_id):
    # KADEME hesapta kullanilmaz ama yayimlanan tabloya yanlis yazilirsa
    # (ornegin 0,466 skorlu bir ilceye 3. kademe) kaynaga guveni zedeler.
    for row in _read_semicolon_csv(CITIES_DIR / city_id / "sege_2022_ilce.csv"):
        assert _expected_kademe(float(row["SKOR"])) == int(row["KADEME"]), (city_id, row)
