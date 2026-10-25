import pytest

from core.paths import city_data_proc, city_data_raw, resolve_pbf_path, year_paths


def test_resolve_pbf_path_prefers_standard_name(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths.city_data_raw", lambda city_id: tmp_path)
    (tmp_path / "testcity.osm.pbf").touch()
    (tmp_path / "aegean-latest.osm.pbf").touch()

    assert resolve_pbf_path("testcity") == tmp_path / "testcity.osm.pbf"


def test_resolve_pbf_path_falls_back_to_legacy_izmir_name(tmp_path, monkeypatch):
    # Şehir ayrımı eklenmeden önce İzmir'in diskte zaten indirilmiş
    # `aegean-latest.osm.pbf` dosyası var - yeniden indirmeyi tetiklememesi
    # gerekir (bkz. core/paths.py, resolve_pbf_path docstring'i).
    monkeypatch.setattr("core.paths.city_data_raw", lambda city_id: tmp_path)
    (tmp_path / "aegean-latest.osm.pbf").touch()

    assert resolve_pbf_path("izmir") == tmp_path / "aegean-latest.osm.pbf"


def test_resolve_pbf_path_returns_standard_name_when_neither_exists(tmp_path, monkeypatch):
    # Yeni bir şehir için legacy dosya hiç var olmaz - standart ad
    # döndürülüp indirme akışına bırakılmalı.
    monkeypatch.setattr("core.paths.city_data_raw", lambda city_id: tmp_path)

    assert resolve_pbf_path("newcity") == tmp_path / "newcity.osm.pbf"


@pytest.mark.parametrize("year", ["../outside", "/tmp/outside", "2024/../../outside", "２０２４"])
def test_year_paths_rejects_unsafe_year_components(year):
    with pytest.raises(ValueError, match="year"):
        year_paths("izmir", year, "2024")


@pytest.mark.parametrize("city_id", ["../outside", "/tmp/outside", "izmir/../../outside"])
def test_city_data_paths_reject_unsafe_city_ids(city_id):
    with pytest.raises(ValueError, match="city"):
        city_data_raw(city_id)
    with pytest.raises(ValueError, match="city"):
        city_data_proc(city_id)


def test_year_paths_keeps_valid_year_layout(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths.city_data_raw", lambda city_id: tmp_path / "raw" / city_id)
    monkeypatch.setattr("core.paths.city_data_proc", lambda city_id: tmp_path / "processed" / city_id)

    raw, processed = year_paths("izmir", "2024", "2026")

    assert raw == tmp_path / "raw" / "izmir" / "2024"
    assert processed == tmp_path / "processed" / "izmir" / "2024"
