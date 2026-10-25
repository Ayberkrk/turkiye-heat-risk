import pytest

from core.cache import atomic_output_path, is_cache_valid, write_cache_meta


def test_atomic_output_path_replaces_only_after_success(tmp_path):
    output = tmp_path / "result.geojson"
    output.write_text("old result")

    with pytest.raises(RuntimeError, match="interrupted"):
        with atomic_output_path(output) as temporary:
            assert temporary.name == "result.part.geojson"
            temporary.write_text("partial result")
            raise RuntimeError("interrupted")

    assert output.read_text() == "old result"
    assert not (tmp_path / "result.part.geojson").exists()


def test_atomic_output_path_publishes_completed_file(tmp_path):
    output = tmp_path / "result.tif"
    with atomic_output_path(output) as temporary:
        temporary.write_bytes(b"complete")

    assert output.read_bytes() == b"complete"
    assert not (tmp_path / "result.part.tif").exists()


def test_missing_file_is_invalid(tmp_path):
    output_path = tmp_path / "roads_with_hvi.geojson"
    assert is_cache_valid(output_path, version=1) is False


def test_missing_meta_file_is_invalid(tmp_path):
    # Bu mekanizmadan önce üretilmiş bir dosya olabilir - yan meta dosyası
    # yoksa güvenli taraf yeniden hesaplamaktır.
    output_path = tmp_path / "roads_with_hvi.geojson"
    output_path.write_text("{}")
    assert is_cache_valid(output_path, version=1) is False


def test_matching_version_is_valid(tmp_path):
    output_path = tmp_path / "roads_with_hvi.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=3)
    assert is_cache_valid(output_path, version=3) is True


def test_mismatched_version_is_invalid(tmp_path):
    output_path = tmp_path / "roads_with_hvi.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=2)
    assert is_cache_valid(output_path, version=3) is False


def test_force_always_invalidates(tmp_path):
    output_path = tmp_path / "roads_with_hvi.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=3)
    assert is_cache_valid(output_path, version=3, force=True) is False


def test_corrupt_meta_file_is_invalid(tmp_path):
    output_path = tmp_path / "roads_with_hvi.geojson"
    output_path.write_text("{}")
    (tmp_path / "roads_with_hvi.geojson.meta.json").write_text("not json")
    assert is_cache_valid(output_path, version=1) is False


def test_matching_input_fingerprint_is_valid(tmp_path):
    output_path = tmp_path / "roads_timeseries.geojson"
    output_path.write_text("{}")
    inputs = {"city": "izmir", "years": ["2020", "2026"], "bbox": [27.0, 38.0, 28.0, 39.0]}
    write_cache_meta(output_path, version=2, fingerprint=inputs)

    assert is_cache_valid(output_path, version=2, fingerprint=inputs) is True


def test_changed_input_fingerprint_invalidates_cache(tmp_path):
    output_path = tmp_path / "roads_timeseries.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=2, fingerprint={"buffer_m": 10})

    assert is_cache_valid(output_path, version=2, fingerprint={"buffer_m": 30}) is False


def test_fingerprint_key_order_does_not_change_cache_identity(tmp_path):
    output_path = tmp_path / "roads_timeseries.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=2, fingerprint={"year": "2026", "city": "izmir"})

    assert is_cache_valid(output_path, version=2, fingerprint={"city": "izmir", "year": "2026"}) is True


def test_cache_details_are_written_with_fingerprinted_metadata(tmp_path):
    import json

    output_path = tmp_path / "roads_timeseries.geojson"
    output_path.write_text("{}")
    write_cache_meta(output_path, version=2, fingerprint={"year": "2026"},
                     details={"coverage_fraction": 0.75})
    meta = json.loads((tmp_path / "roads_timeseries.geojson.meta.json").read_text())

    assert meta["details"]["coverage_fraction"] == 0.75
    assert len(meta["fingerprint_sha256"]) == 64
    assert not (tmp_path / "roads_timeseries.geojson.meta.json.part").exists()
