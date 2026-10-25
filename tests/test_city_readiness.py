import json
import sys
import types
from pathlib import Path

import pandas as pd
import yaml

from core.city_readiness import (
    _city_static_errors,
    _csv_data_errors,
    _published_status,
    validate_city_readiness,
    validate_city_registry,
)
from core.hvi import HVI_FORMULA_VERSION


def _minimal_config(adapter="cities.sample.adapter", crs="EPSG:32635"):
    return {
        "city": {"name": "Sample", "bbox": [27.0, 38.0, 27.5, 38.5], "crs": crs,
                 "attribution": "Population: national statistics 2025; SEGE-2022."},
        "osm": {"pbf_url": "https://example.org/turkey.osm.pbf", "highway_types": ["primary"],
                "admin_level_ilce": 6, "admin_level_mahalle": 8},
        "population": {"adapter": adapter},
        "roads": {"buffer_meters": 10},
    }


def _write_city_tables(city_dir: Path, population_rows=None, sege_rows=None):
    city_dir.mkdir(parents=True, exist_ok=True)
    population = pd.DataFrame(population_rows or [
        {"ILCE": "Sample", "NUFUS": 1000, "YASLI_ORAN": 0.1, "COCUK_ORAN": 0.2}
    ])
    sege = pd.DataFrame(sege_rows or [{"ILCE": "Sample", "SKOR": 0.5}])
    population.to_csv(city_dir / "ilce_nufus.csv", sep=";", index=False)
    sege.to_csv(city_dir / "sege_2022_ilce.csv", sep=";", index=False)


def test_all_registered_cities_pass_offline_structural_checks():
    report = validate_city_registry(docs_dir=Path("docs"))

    assert report["configured_city_count"] > 0
    assert report["structurally_valid_count"] == 70
    assert report["source_values_independently_verified"] == 0
    assert report["osm_coverages_measured"] == 0
    assert all(city["errors"] == [] for city in report["cities"])
    assert {city["source_values"] for city in report["cities"]} == {"not_independently_verified"}


def test_city_static_checks_reject_geographic_crs_for_meter_based_analysis():
    errors = _city_static_errors("sample", _minimal_config(crs="EPSG:4326"))

    assert any("metre tabanlı projeksiyon" in error for error in errors)


def test_city_static_checks_accept_projected_meter_crs(monkeypatch):
    fake_adapter = types.ModuleType("cities.sample.adapter")
    fake_adapter.fetch_population_data = lambda config: {}
    fake_adapter.build_neighborhood_layer = lambda pbf_path, population_paths, config: None
    monkeypatch.setitem(sys.modules, "cities.sample.adapter", fake_adapter)

    errors = _city_static_errors("sample", _minimal_config())

    assert errors == []


def test_city_static_checks_validate_adapter_call_signatures(monkeypatch):
    fake_adapter = types.ModuleType("cities.sample.adapter")
    fake_adapter.fetch_population_data = lambda: {}
    fake_adapter.build_neighborhood_layer = lambda pbf_path, population_paths, config: None
    monkeypatch.setitem(sys.modules, "cities.sample.adapter", fake_adapter)

    errors = _city_static_errors("sample", _minimal_config())

    assert any("fetch_population_data() 1 pozisyonel argüman" in error for error in errors)


def test_csv_quality_checks_reject_age_share_over_one(tmp_path):
    _write_city_tables(tmp_path, population_rows=[
        {"ILCE": "Sample", "NUFUS": 1000, "YASLI_ORAN": 0.7, "COCUK_ORAN": 0.4}
    ])

    errors = _csv_data_errors("sample", tmp_path, "cities.adana.adapter")

    assert any("toplamı 1'i aşıyor" in error for error in errors)


def test_csv_quality_checks_reject_keys_that_collide_after_normalization(tmp_path):
    _write_city_tables(tmp_path, population_rows=[
        {"ILCE": "Cigli", "NUFUS": 1000, "YASLI_ORAN": 0.1, "COCUK_ORAN": 0.2},
        {"ILCE": "Çiğli", "NUFUS": 2000, "YASLI_ORAN": 0.2, "COCUK_ORAN": 0.3},
    ], sege_rows=[{"ILCE": "Cigli", "SKOR": 0.5}, {"ILCE": "Çiğli", "SKOR": 0.8}])

    errors = _csv_data_errors("sample", tmp_path, "cities.adana.adapter")

    assert any("normalize edilmiş ilçe anahtarları tekrarlı" in error for error in errors)


def test_izmir_dynamic_adapter_does_not_require_a_bundled_population_csv(tmp_path):
    (tmp_path / "sege_2022_ilce.csv").write_text("ILCE;SKOR\nKonak;1.2\n", encoding="utf-8")

    assert _csv_data_errors("izmir", tmp_path, "cities.izmir.adapter") == []


def test_published_map_status_distinguishes_current_unversioned_and_missing(tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    (current / "index.html").write_text("", encoding="utf-8")
    (current / "manifest.json").write_text(json.dumps({"versions": {"hvi_formula_version": HVI_FORMULA_VERSION}}))
    unversioned = tmp_path / "unversioned"
    unversioned.mkdir()
    (unversioned / "index.html").write_text("", encoding="utf-8")

    assert _published_status("current", tmp_path) == "current"
    assert _published_status("unversioned", tmp_path) == "unversioned"
    assert _published_status("missing", tmp_path) == "not_published"


def test_single_city_report_keeps_source_verification_distinct(tmp_path, monkeypatch):
    city_dir = tmp_path / "sample"
    city_dir.mkdir()
    (city_dir / "config.yaml").write_text(yaml.safe_dump(_minimal_config()), encoding="utf-8")
    _write_city_tables(city_dir)
    fake_adapter = types.ModuleType("cities.sample.adapter")
    fake_adapter.fetch_population_data = lambda config: {}
    fake_adapter.build_neighborhood_layer = lambda pbf_path, population_paths, config: None
    monkeypatch.setitem(sys.modules, "cities.sample.adapter", fake_adapter)

    report = validate_city_readiness("sample", tmp_path)

    assert report["errors"] == []
    assert report["source_attribution"] == "present_not_verified"
    assert report["source_values"] == "not_independently_verified"
    assert report["osm_coverage"] == "not_measured"
