import sys
import types

import pytest

import validate_city
from core.adapter_contract import (
    OPTIONAL_ADAPTER_PARAM_COUNTS,
    REQUIRED_ADAPTER_PARAM_COUNTS,
    signature_param_count_error,
)
from validate_city import validate

# --- signature_param_count_error: saf, adapter imzasını gerçek çağrı yerindeki
# (hvi.py) argüman sayısıyla karşılaştırır - isim değil sayı, çünkü adapter
# yazarları parametrelere farklı isim verebilir. ---

def testsignature_param_count_error_accepts_matching_signature():
    def fetch_population_data(config):
        pass
    assert signature_param_count_error(fetch_population_data, "fetch_population_data", 1) is None


def testsignature_param_count_error_rejects_too_few_parameters():
    def fetch_population_data():
        pass
    err = signature_param_count_error(fetch_population_data, "fetch_population_data", 1)
    assert err is not None
    assert "fetch_population_data" in err


def testsignature_param_count_error_rejects_too_many_required_parameters():
    # Çağrı yerinde tek argümanla çağrılacak ama fonksiyon 2 zorunlu
    # parametre istiyor - gerçek çağrıda TypeError ile patlar.
    def build_neighborhood_layer(pbf_path, population_paths):
        pass
    err = signature_param_count_error(build_neighborhood_layer, "build_neighborhood_layer", 1)
    assert err is not None


def testsignature_param_count_error_rejects_required_keyword_only_parameter():
    def fetch_population_data(config, *, api_key):
        pass

    err = signature_param_count_error(fetch_population_data, "fetch_population_data", 1)

    assert err is not None
    assert "api_key" in err


def testsignature_param_count_error_rejects_non_callable_adapter_attribute():
    err = signature_param_count_error("not callable", "fetch_population_data", 1)

    assert err is not None
    assert "çağrılabilir değil" in err


def testsignature_param_count_error_allows_extra_optional_parameters():
    # Fazladan opsiyonel (varsayılan değerli) bir parametre - gerçek
    # çağrıda sorun çıkarmaz, hata verilmemeli.
    def fetch_population_data(config, cache_dir=None):
        pass
    assert signature_param_count_error(fetch_population_data, "fetch_population_data", 1) is None


def testsignature_param_count_error_allows_var_positional():
    # *args kabul eden esnek bir imza her zaman geçerli sayılmalı.
    def build_neighborhood_layer(*args):
        pass
    assert signature_param_count_error(build_neighborhood_layer, "build_neighborhood_layer", 3) is None


def test_required_adapter_param_counts_matches_real_call_sites():
    # hvi.py:181 adapter.fetch_population_data(config) - 1 argüman
    # hvi.py:183 adapter.build_neighborhood_layer(pbf_path, population_paths, config) - 3 argüman
    assert REQUIRED_ADAPTER_PARAM_COUNTS == {
        "fetch_population_data": 1,
        "build_neighborhood_layer": 3,
    }
    assert OPTIONAL_ADAPTER_PARAM_COUNTS == {
        "refresh_population_data": 1,
        "load_cached_population_data": 1,
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


def test_validate_checks_optional_population_refresh_hook(tmp_path, monkeypatch, _no_network):
    monkeypatch.setattr(validate_city, "CITIES_DIR", tmp_path)
    monkeypatch.setattr("core.city_config.CITIES_DIR", tmp_path)

    adapter_name = "test_validate_city_bad_refresh_hook"
    _write_config_yaml(tmp_path, "testcity", adapter_name)
    _register_fake_adapter(
        adapter_name,
        fetch_population_data=lambda config: None,
        build_neighborhood_layer=lambda pbf_path, population_paths, config: None,
    )
    sys.modules[adapter_name].refresh_population_data = lambda config, token: None

    errors = validate("testcity")

    assert any("refresh_population_data" in error for error in errors)


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


def test_validate_offline_skips_source_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_city, "CITIES_DIR", tmp_path)
    monkeypatch.setattr("core.city_config.CITIES_DIR", tmp_path)
    _write_config_yaml(tmp_path, "testcity", "test_validate_city_offline_adapter")
    _register_fake_adapter(
        "test_validate_city_offline_adapter",
        fetch_population_data=lambda config: None,
        build_neighborhood_layer=lambda pbf_path, population_paths, config: None,
    )

    def unexpected_request(*args, **kwargs):
        raise AssertionError("offline validation must not contact source URLs")

    monkeypatch.setattr(validate_city.requests, "head", unexpected_request)
    monkeypatch.setattr(validate_city.requests, "get", unexpected_request)

    assert validate("testcity", check_sources=False) == []


@pytest.mark.parametrize("city_id", ["../outside", "/tmp/outside", "izmir/../../outside"])
def test_validate_rejects_unsafe_city_ids_before_reading_config(city_id):
    errors = validate(city_id, check_sources=False)

    assert len(errors) == 1
    assert "Geçersiz şehir kimliği" in errors[0]


@pytest.mark.parametrize("coverage", ["-0.1", "1.1", "nan", "inf"])
def test_cli_rejects_invalid_coverage_threshold(monkeypatch, coverage):
    monkeypatch.setattr(sys, "argv", ["validate_city.py", "izmir", "--osm-coverage", "--min-coverage", coverage])

    with pytest.raises(SystemExit) as error:
        validate_city.main()

    assert error.value.code == 2


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
                        lambda config, path, offline=False: {"mahalle": 35, "yol": 2395, "ilce": ["Burdur Merkez"], "coverage": 0.0})

    errors = validate_city._coverage_errors(_fake_config(), pbf, 0.6)

    assert len(errors) == 1
    assert "%0.0" in errors[0] and "Burdur Merkez" in errors[0]


def test_coverage_errors_accepts_sufficient_coverage(tmp_path, monkeypatch):
    pbf = tmp_path / "x.osm.pbf"
    pbf.write_bytes(b"")
    monkeypatch.setattr(validate_city, "measure_city_coverage",
                        lambda config, path, offline=False: {"mahalle": 82, "yol": 14000, "ilce": ["Toroslar"], "coverage": 0.85})

    assert validate_city._coverage_errors(_fake_config(), pbf, 0.6) == []


def test_coverage_errors_forwards_offline_mode(tmp_path, monkeypatch):
    pbf = tmp_path / "x.osm.pbf"
    pbf.write_bytes(b"")
    calls = []

    def fake_measure(config, path, offline=False):
        calls.append(offline)
        return {"mahalle": 82, "yol": 14000, "ilce": ["Toroslar"], "coverage": 0.85}

    monkeypatch.setattr(validate_city, "measure_city_coverage", fake_measure)

    assert validate_city._coverage_errors(_fake_config(), pbf, 0.6, offline=True) == []
    assert calls == [True]
