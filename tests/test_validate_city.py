import sys
import types

import pytest

import validate_city
from validate_city import REQUIRED_ADAPTER_PARAM_COUNTS, _signature_param_count_error, validate


# --- _signature_param_count_error: saf, adapter imzasını gerçek çağrı yerindeki
# (hvi.py) argüman sayısıyla karşılaştırır - isim değil sayı, çünkü adapter
# yazarları parametrelere farklı isim verebilir. ---

def test_signature_param_count_error_accepts_matching_signature():
    def fetch_population_data(config):
        pass
    assert _signature_param_count_error(fetch_population_data, "fetch_population_data", 1) is None


def test_signature_param_count_error_rejects_too_few_parameters():
    def fetch_population_data():
        pass
    err = _signature_param_count_error(fetch_population_data, "fetch_population_data", 1)
    assert err is not None
    assert "fetch_population_data" in err


def test_signature_param_count_error_rejects_too_many_required_parameters():
    # Çağrı yerinde tek argümanla çağrılacak ama fonksiyon 2 zorunlu
    # parametre istiyor - gerçek çağrıda TypeError ile patlar.
    def build_neighborhood_layer(pbf_path, population_paths):
        pass
    err = _signature_param_count_error(build_neighborhood_layer, "build_neighborhood_layer", 1)
    assert err is not None


def test_signature_param_count_error_allows_extra_optional_parameters():
    # Fazladan opsiyonel (varsayılan değerli) bir parametre - gerçek
    # çağrıda sorun çıkarmaz, hata verilmemeli.
    def fetch_population_data(config, cache_dir=None):
        pass
    assert _signature_param_count_error(fetch_population_data, "fetch_population_data", 1) is None


def test_signature_param_count_error_allows_var_positional():
    # *args kabul eden esnek bir imza her zaman geçerli sayılmalı.
    def build_neighborhood_layer(*args):
        pass
    assert _signature_param_count_error(build_neighborhood_layer, "build_neighborhood_layer", 3) is None


def test_required_adapter_param_counts_matches_real_call_sites():
    # hvi.py:181 adapter.fetch_population_data(config) - 1 argüman
    # hvi.py:183 adapter.build_neighborhood_layer(pbf_path, population_paths, config) - 3 argüman
    assert REQUIRED_ADAPTER_PARAM_COUNTS == {
        "fetch_population_data": 1,
        "build_neighborhood_layer": 3,
    }


# --- validate(): uçtan uca, network monkeypatch'lenerek ---

def _write_config_yaml(cities_dir, city_id, adapter_path, crs="EPSG:32635"):
    city_dir = cities_dir / city_id
    city_dir.mkdir(parents=True)
    (city_dir / "config.yaml").write_text(f"""
city:
  name: "Test City"
  bbox: [27.0, 38.0, 27.5, 38.5]
  crs: "{crs}"
osm:
  pbf_url: "https://example.com/test.osm.pbf"
  highway_types: ["primary"]
  admin_level_ilce: 6
  admin_level_mahalle: 8
population:
  adapter: "{adapter_path}"
""")


def _register_fake_adapter(module_name: str, fetch_population_data, build_neighborhood_layer):
    fake_module = types.ModuleType(module_name)
    fake_module.fetch_population_data = fetch_population_data
    fake_module.build_neighborhood_layer = build_neighborhood_layer
    sys.modules[module_name] = fake_module


@pytest.fixture
def _no_network(monkeypatch):
    # OSM pbf / CKAN erişilebilirlik kontrolleri network gerektiriyor -
    # bu testler sadece adapter imza/CRS doğrulamasını hedefliyor.
    class _FakeResponse:
        status_code = 200
    monkeypatch.setattr(validate_city.requests, "head", lambda *a, **kw: _FakeResponse())
    monkeypatch.setattr(validate_city.requests, "get", lambda *a, **kw: _FakeResponse())


def test_validate_reports_adapter_signature_mismatch(tmp_path, monkeypatch, _no_network):
    monkeypatch.setattr(validate_city, "CITIES_DIR", tmp_path)
    monkeypatch.setattr("core.city_config.CITIES_DIR", tmp_path)

    adapter_name = "test_validate_city_bad_adapter"
    _write_config_yaml(tmp_path, "testcity", adapter_name)
    _register_fake_adapter(
        adapter_name,
        fetch_population_data=lambda: None,  # eksik `config` parametresi
        build_neighborhood_layer=lambda pbf_path, population_paths, config: None,
    )

    errors = validate("testcity")

    assert any("fetch_population_data" in e for e in errors)


def test_validate_reports_invalid_crs(tmp_path, monkeypatch, _no_network):
    monkeypatch.setattr(validate_city, "CITIES_DIR", tmp_path)
    monkeypatch.setattr("core.city_config.CITIES_DIR", tmp_path)

    _write_config_yaml(tmp_path, "testcity", "does.not.matter", crs="not-a-crs")

    errors = validate("testcity")

    assert any("crs" in e for e in errors)


def test_validate_passes_with_well_formed_adapter_and_crs(tmp_path, monkeypatch, _no_network):
    monkeypatch.setattr(validate_city, "CITIES_DIR", tmp_path)
    monkeypatch.setattr("core.city_config.CITIES_DIR", tmp_path)

    adapter_name = "test_validate_city_good_adapter"
    _write_config_yaml(tmp_path, "testcity", adapter_name)
    _register_fake_adapter(
        adapter_name,
        fetch_population_data=lambda config: None,
        build_neighborhood_layer=lambda pbf_path, population_paths, config: None,
    )

    assert validate("testcity") == []


# --- --osm-coverage: gerçek OSM sınırlarıyla HVI kapsamı kontrolü -----------

def _fake_config():
    return object()


def test_coverage_errors_reports_missing_pbf(tmp_path):
    errors = validate_city._coverage_errors(_fake_config(), tmp_path / "yok.osm.pbf", 0.6)
    assert len(errors) == 1 and "bulunamadı" in errors[0]


def test_coverage_errors_flags_low_coverage(tmp_path, monkeypatch):
    pbf = tmp_path / "x.osm.pbf"
    pbf.write_bytes(b"")
    monkeypatch.setattr(validate_city, "measure_city_coverage",
                        lambda config, path: {"mahalle": 35, "yol": 2395, "ilce": ["Burdur Merkez"], "coverage": 0.0})

    errors = validate_city._coverage_errors(_fake_config(), pbf, 0.6)

    assert len(errors) == 1
    assert "%0.0" in errors[0] and "Burdur Merkez" in errors[0]


def test_coverage_errors_accepts_sufficient_coverage(tmp_path, monkeypatch):
    pbf = tmp_path / "x.osm.pbf"
    pbf.write_bytes(b"")
    monkeypatch.setattr(validate_city, "measure_city_coverage",
                        lambda config, path: {"mahalle": 82, "yol": 14000, "ilce": ["Toroslar"], "coverage": 0.85})

    assert validate_city._coverage_errors(_fake_config(), pbf, 0.6) == []
