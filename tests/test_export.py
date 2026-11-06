import json
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

import core.export as export
from core.city_config import CityConfig

YEARS = ["2020", "2026"]
N = 120


def _make_config() -> CityConfig:
    return CityConfig(
        city_id="testcity", name="Test Şehri", bbox=[27.0, 38.0, 27.2, 38.2], crs="EPSG:32635", max_cloud_cover=30,
        osm_pbf_url="", drive_highway_types=["residential"], admin_level_ilce="6",
        admin_level_mahalle="8", population_adapter_path="unused",
    )


def _roads(n: int = N) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(0)
    mahalle = [f"M{i % 4}" for i in range(n)]
    data = {
        "name": [f"Sokak {i}" if i % 3 else None for i in range(n)],
        "highway": ["residential"] * n,
        "length": rng.uniform(50, 400, n),
        "mahalle_adi": mahalle,
        "ilce_adi": ["Doğu" if m in ("M0", "M1") else "Batı" for m in mahalle],
        "nufus_yogunlugu": rng.uniform(100, 30000, n),
        "nufus_yogunlugu_birim": rng.uniform(100, 30000, n),
        "bina_yogunlugu": rng.uniform(10, 900, n),
        "yasli_oran": rng.uniform(0.08, 0.2, n),
        "cocuk_oran": rng.uniform(0.12, 0.3, n),
        "sosyoekonomik_skor": rng.normal(0, 1, n),
        "dist_saglik_m": rng.uniform(10, 2000, n),
        "dist_yesil_m": rng.uniform(10, 900, n),
        "_label_nufus": ["yoğun"] * n,  # iç sütun: pakete girmemeli
    }
    cats = export.CATEGORY_ORDER_5
    for k, year in enumerate(YEARS):
        # M0 mahallesi bilerek en riskli: sıralama testi buna dayanır.
        pct = np.where(np.array(mahalle) == "M0", 85.0, rng.uniform(5, 70, n)) + k
        data[f"hvi_score_{year}"] = pct
        data[f"hvi_percentage_{year}"] = pct
        data[f"hvi_category_{year}"] = [cats[min(int(v // 20), 4)] for v in pct]
        for group in ("hazard", "exposure", "vulnerability"):
            data[f"group_{group}_{year}"] = rng.uniform(0, 1, n)
        data[f"lst_mean_{year}"] = rng.uniform(35, 50, n)
        data[f"ndvi_mean_{year}"] = rng.uniform(0.05, 0.6, n)
    data["hvi_percentage_2026"][0] = np.nan  # skorsuz yol
    data["hvi_category_2026"][0] = "nan"
    geometry = [LineString([(27 + 0.001 * (i % 30), 38 + 0.004 * (i // 30)),
                            (27 + 0.001 * (i % 30) + 0.0008, 38 + 0.004 * (i // 30))]) for i in range(n)]
    return gpd.GeoDataFrame(data, geometry=geometry, crs="EPSG:4326")


def _polys() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"mahalle_adi": ["M0", "M1", "M2", "M3"], "ilce_adi": ["Doğu", "Doğu", "Batı", "Batı"]},
        geometry=[box(27.0, 38.0, 27.05, 38.02), box(27.05, 38.0, 27.1, 38.02),
                  box(27.0, 38.02, 27.05, 38.04), box(27.05, 38.02, 27.1, 38.04)], crs="EPSG:4326",
    )


@pytest.fixture
def package(monkeypatch, tmp_path):
    monkeypatch.setattr("core.export.city_data_proc", lambda city_id: tmp_path / "proc")
    monkeypatch.setattr("core.export.DOCS_DIR", tmp_path / "docs")
    out, docs = tmp_path / "out" / "paket", tmp_path / "docs" / "testcity" / "indir"
    zip_path = export.export_city_package(_make_config(), roads=_roads(), mahalle_polys=_polys(),
                                          out_dir=out, docs_dir=docs)
    return zip_path, out, docs


def test_package_contains_every_promised_file(package):
    zip_path, out, docs = package
    names = {p.name for p in out.iterdir()}
    assert {"testcity_isi_riski.xlsx", "testcity_isi_riski.gpkg", "testcity_mahalleler.csv", "testcity_ilceler.csv",
            "testcity_oncelikli_yollar.csv", "testcity_yollar.csv", "sutun_sozlugu.csv", "ozet.html", "OKUBENI.txt",
            "harita.png", "en_riskli_mahalleler.png", "risk_kaynagi.png", "kategori_dagilimi.png"} <= names
    with zipfile.ZipFile(zip_path) as archive:
        assert {f"testcity_veri_paketi/{n}" for n in names} == set(archive.namelist())
    # Site kopyası küçük kalır: büyük yol katmanı yalnızca zip'te.
    site = {p.name for p in docs.iterdir()}
    assert "testcity_isi_riski.xlsx" in site and "ozet.html" in site
    assert "testcity_isi_riski.gpkg" not in site and "testcity_yollar.csv" not in site


def test_workbook_sheets_and_neighbourhood_ranking(package):
    _, out, _ = package
    sheets = pd.read_excel(out / "testcity_isi_riski.xlsx", sheet_name=None)
    assert list(sheets) == ["Özet", "Mahalleler", "İlçeler", "Öncelikli yollar", "Sütun sözlüğü",
                            "Kaynaklar ve lisans"]
    mahalle = sheets["Mahalleler"]
    assert mahalle.loc[0, "mahalle_adi"] == "M0" and mahalle.loc[0, "sira"] == 1
    assert mahalle["yol_sayisi"].sum() == N - 1  # skorsuz yol sayılmaz
    assert set(mahalle["guvenilir_ortalama"]) == {"Evet"}
    assert "hvi_degisim" in mahalle
    priority = sheets["Öncelikli yollar"]
    assert priority["hvi_yuzde_2026"].is_monotonic_decreasing
    assert {"enlem", "boylam", "osm_ad"} <= set(priority.columns)
    assert not any(c.startswith("_") for c in priority.columns)


def test_dictionary_documents_every_exported_column(package):
    _, out, _ = package
    sheets = pd.read_excel(out / "testcity_isi_riski.xlsx", sheet_name=None)
    documented = set(sheets["Sütun sözlüğü"]["sutun"])
    for name in ("Mahalleler", "İlçeler", "Öncelikli yollar"):
        assert set(sheets[name].columns) <= documented, name


def test_license_sheet_states_odbl_for_osm_derived_data(package):
    _, out, _ = package
    sources = pd.read_excel(out / "testcity_isi_riski.xlsx", sheet_name="Kaynaklar ve lisans")
    assert sources["Lisans"].str.contains("ODbL").any()
    assert sources["Lisans"].str.contains("CC BY 4.0").any()
    assert "ODbL" in (out / "OKUBENI.txt").read_text(encoding="utf-8")


def test_geopackage_has_roads_and_neighbourhood_layers(package):
    import pyogrio

    _, out, _ = package
    layers = {name for name, _ in pyogrio.list_layers(out / "testcity_isi_riski.gpkg")}
    assert layers == {"yollar", "mahalleler"}
    polys = gpd.read_file(out / "testcity_isi_riski.gpkg", layer="mahalleler")
    assert len(polys) == 4 and "hvi_ort_2026" in polys


def test_report_is_self_describing_and_escapes_names(monkeypatch, tmp_path):
    roads = _roads()
    roads.loc[roads["mahalle_adi"] == "M0", "mahalle_adi"] = "<b>Yeni</b>"
    monkeypatch.setattr("core.export.city_data_proc", lambda city_id: tmp_path / "proc")
    monkeypatch.setattr("core.export.DOCS_DIR", tmp_path / "docs")
    out = tmp_path / "out" / "paket"
    export.export_city_package(_make_config(), roads=roads, include_polygons=False, out_dir=out,
                               docs_dir=tmp_path / "docs" / "testcity" / "indir")
    html = (out / "ozet.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;Yeni&lt;/b&gt;" in html and "<b>Yeni</b>" not in html
    assert export.DISCLAIMER in html
    assert "releases/latest/download/testcity_veri_paketi.zip" in html
    assert "Korkmaz" in html  # atıf CITATION.cff'ten


def test_uncertainty_columns_are_joined_by_road_id(monkeypatch, tmp_path):
    from core.uncertainty import UncertaintySettings

    roads = _roads()
    # Ana pipeline'ın uncertainty adımıyla aynı yol: tüm yıllarda skoru olan yollar.
    proc = tmp_path / "proc"
    unc_dir = proc / "uncertainty"
    unc_dir.mkdir(parents=True)
    scored = roads.index[roads["hvi_percentage_2026"].notna()]
    fake = gpd.GeoDataFrame({"yol_no": scored, "olasilik_ilk_yuzde10": np.linspace(0, 1, len(scored)),
                             "sira_p05": 0.1, "sira_p95": 0.9}, geometry=roads.geometry[scored], crs=roads.crs)
    fake.to_file(unc_dir / "belirsizlik_yollar.geojson", driver="GeoJSON")
    (unc_dir / "belirsizlik_ozet.json").write_text(json.dumps({
        "year": "2026", "share_of_default_top10_stable_ge_90pct": 0.8, "spearman_vs_default": {"p50": 0.95},
        "settings": {"runs": UncertaintySettings().runs},
    }), encoding="utf-8")
    pd.DataFrame({"mahalle": ["M0 (Doğu)"], "sira_medyan": [1.0], "olasilik_ilk_5": [1.0],
                  "olasilik_ilk_20": [1.0]}).to_csv(unc_dir / "belirsizlik_mahalleler.csv", index=False)
    monkeypatch.setattr("core.export.city_data_proc", lambda city_id: proc)
    monkeypatch.setattr("core.export.DOCS_DIR", tmp_path / "docs")
    out = tmp_path / "out" / "paket"
    export.export_city_package(_make_config(), roads=roads, include_polygons=False, out_dir=out,
                               docs_dir=tmp_path / "docs" / "testcity" / "indir")

    all_roads = pd.read_csv(out / "testcity_yollar.csv")
    assert pd.isna(all_roads.loc[0, "olasilik_ilk_yuzde10"])  # skorsuz yol
    assert all_roads.loc[scored[-1], "olasilik_ilk_yuzde10"] == pytest.approx(1.0)
    mahalle = pd.read_csv(out / "testcity_mahalleler.csv")
    assert mahalle.loc[mahalle["mahalle_adi"] == "M0", "olasilik_ilk_5"].iloc[0] == 1.0
    summary = pd.read_excel(out / "testcity_isi_riski.xlsx", sheet_name="Özet")
    assert summary["Başlık"].str.contains("Belirsizlik").any()


def test_missing_scores_is_a_clear_error(tmp_path):
    roads = _roads().drop(columns=[f"hvi_score_{y}" for y in YEARS])
    with pytest.raises(ValueError, match="hvi_score"):
        export.export_city_package(_make_config(), roads=roads, include_polygons=False, out_dir=tmp_path / "o",
                                   docs_dir=tmp_path / "d")
