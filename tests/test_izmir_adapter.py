from types import SimpleNamespace

import pytest

from cities.izmir import adapter
from core.city_config import CityConfig


def _config() -> CityConfig:
    return CityConfig(
        city_id="izmir", name="İzmir", bbox=[26.5, 38.0, 27.5, 38.5], crs="EPSG:32635",
        max_cloud_cover=30, osm_pbf_url="https://example.test/izmir.pbf",
        drive_highway_types=["primary"], admin_level_ilce="6", admin_level_mahalle="8",
        population_adapter_path="cities.izmir.adapter",
        raw={"population": {"ckan_base": "https://data.example.test", "datasets": {"nufus": "pkg"}}},
    )


def test_izmir_population_cache_can_be_refreshed_explicitly(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "city_data_raw", lambda city_id: tmp_path)
    monkeypatch.setattr(adapter, "ckan_csv_url", lambda base, package_id: "https://data.example.test/nufus.csv")
    responses = iter([b"ILCE;NUFUS\nKonak;100\n", b"ILCE;NUFUS\nKonak;200\n"])
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        content = next(responses)
        return SimpleNamespace(content=content, raise_for_status=lambda: None)

    monkeypatch.setattr(adapter.requests, "get", fake_get)
    config = _config()

    paths = adapter.fetch_population_data(config)
    assert paths["nufus"].read_bytes() == b"ILCE;NUFUS\nKonak;100\n"

    # Ordinary runs keep their cache; the explicit adapter hook replaces it.
    assert adapter.fetch_population_data(config)["nufus"].read_bytes() == b"ILCE;NUFUS\nKonak;100\n"
    assert len(calls) == 1
    refreshed = adapter.refresh_population_data(config)
    assert refreshed["nufus"].read_bytes() == b"ILCE;NUFUS\nKonak;200\n"
    assert len(calls) == 2
    assert not (tmp_path / "population" / "nufus.part.csv").exists()


@pytest.mark.parametrize("bad_content", [
    b"<html>temporary server error</html>",
    b"server temporarily unavailable; retry later",  # non-HTML body that is not a tabular CSV
])
def test_failed_izmir_population_refresh_keeps_previous_file(tmp_path, monkeypatch, bad_content):
    population_dir = tmp_path / "population"
    population_dir.mkdir()
    cached = population_dir / "nufus.csv"
    cached.write_bytes(b"ILCE;NUFUS\nKonak;100\n")
    monkeypatch.setattr(adapter, "city_data_raw", lambda city_id: tmp_path)
    monkeypatch.setattr(adapter, "ckan_csv_url", lambda base, package_id: "https://data.example.test/nufus.csv")
    monkeypatch.setattr(adapter.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        content=bad_content, raise_for_status=lambda: None,
    ))

    with pytest.raises(ValueError):
        adapter.refresh_population_data(_config())

    assert cached.read_bytes() == b"ILCE;NUFUS\nKonak;100\n"
    assert not (population_dir / "nufus.part.csv").exists()


def test_failed_later_dataset_download_keeps_all_cached_tables(tmp_path, monkeypatch):
    population_dir = tmp_path / "population"
    population_dir.mkdir()
    first = population_dir / "first.csv"
    second = population_dir / "second.csv"
    first.write_bytes(b"ILCE;NUFUS\nKonak;100\n")
    second.write_bytes(b"ILCE;NUFUS\nBornova;200\n")
    monkeypatch.setattr(adapter, "city_data_raw", lambda city_id: tmp_path)
    monkeypatch.setattr(adapter, "ckan_csv_url", lambda base, package_id: f"https://data.example.test/{package_id}.csv")

    calls = 0

    def fake_get(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(content=b"ILCE;NUFUS\nKonak;999\n", raise_for_status=lambda: None)
        raise adapter.requests.ConnectionError("temporary network failure")

    monkeypatch.setattr(adapter.requests, "get", fake_get)
    config = _config()
    config.raw["population"]["datasets"] = {"first": "pkg-first", "second": "pkg-second"}

    with pytest.raises(adapter.requests.ConnectionError):
        adapter.refresh_population_data(config)

    assert first.read_bytes() == b"ILCE;NUFUS\nKonak;100\n"
    assert second.read_bytes() == b"ILCE;NUFUS\nBornova;200\n"
    assert not list(population_dir.glob("*.part.csv"))


def test_load_cached_population_data_never_fetches_and_reports_missing_cache(tmp_path, monkeypatch):
    population_dir = tmp_path / "population"
    population_dir.mkdir()
    monkeypatch.setattr(adapter, "city_data_raw", lambda city_id: tmp_path)

    def unexpected_request(*args, **kwargs):
        raise AssertionError("cached-only loader must not access the network")

    monkeypatch.setattr(adapter.requests, "get", unexpected_request)
    config = _config()

    with pytest.raises(FileNotFoundError, match="önce ağ erişimi olan bir ortamda"):
        adapter.load_cached_population_data(config)

    cached = population_dir / "nufus.csv"
    cached.write_text("ILCE;NUFUS\nKonak;100\n", encoding="utf-8")

    assert adapter.load_cached_population_data(config) == {"nufus": cached}
