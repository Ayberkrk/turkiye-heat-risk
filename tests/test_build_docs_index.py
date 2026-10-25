import json

import pytest

import build_docs_index
from core.hvi import HVI_FORMULA_VERSION


def _write_city(docs_dir, city_id, name, formula_version=None):
    city_dir = docs_dir / city_id
    city_dir.mkdir(parents=True)
    (city_dir / "stats.json").write_text(json.dumps({
        "city_id": city_id, "name": name, "years": ["2020", "2026"], "road_count": 100,
        "avg_hvi_percentage": 40.0, "top_risk_mahalle": "A Mahallesi",
    }))
    if formula_version is not None:
        (city_dir / "manifest.json").write_text(json.dumps({"versions": {"hvi_formula_version": formula_version}}))


def test_index_marks_cities_built_with_an_older_formula(tmp_path, monkeypatch):
    # Formül değişince şehirler aynı anda yenilenmeyebilir. Eski formülle
    # kalan harita sayfada işaretlenmeli; manifest'siz haritaların sürümü
    # bilinmediğinden eski olduğu kesinmiş gibi sunulmamalı.
    _write_city(tmp_path, "guncel", "Güncel Şehir", HVI_FORMULA_VERSION)
    _write_city(tmp_path, "eski", "Eski Şehir", HVI_FORMULA_VERSION - 1)
    _write_city(tmp_path, "manifestsiz", "Manifestsiz Şehir")
    _write_city(tmp_path, "bozuk", "Bozuk Manifestli Şehir")
    (tmp_path / "bozuk" / "manifest.json").write_text("{")
    monkeypatch.setattr(build_docs_index, "DOCS_DIR", tmp_path)

    html = build_docs_index.build_index().read_text(encoding="utf-8")

    assert html.count("Eski formülle üretildi") == 1
    assert html.count("Formül sürümü kayıtlı değil; güncelliği bilinmiyor") == 1
    assert html.count("Manifest okunamıyor veya formül sürümü geçersiz") == 1
    # Güncel şehir önce listelenir ve işaret taşımaz.
    guncel, eski = html.index("Güncel Şehir"), html.index("Eski Şehir")
    assert guncel < eski
    assert "Eski formülle üretildi" not in html[guncel:eski]


def test_index_escapes_untrusted_stats_text(tmp_path, monkeypatch):
    _write_city(tmp_path, "ornek", "Örnek Şehir")
    stats_path = tmp_path / "ornek" / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    stats["name"] = '<img src=x onerror="alert(1)">'
    stats["years"] = ['2026<script>alert("year")</script>']
    stats["top_risk_mahalle"] = '<svg onload="alert(2)">'
    stats_path.write_text(json.dumps(stats), encoding="utf-8")
    monkeypatch.setattr(build_docs_index, "DOCS_DIR", tmp_path)

    html = build_docs_index.build_index().read_text(encoding="utf-8")

    assert '<img src=x onerror="alert(1)">' not in html
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in html
    assert '&lt;script&gt;alert(&quot;year&quot;)&lt;/script&gt;' in html
    assert '&lt;svg onload=&quot;alert(2)&quot;&gt;' in html


@pytest.mark.parametrize("bad_stats", ["{", "{}", "[]"])
def test_index_rejects_invalid_city_stats_without_replacing_existing_index(tmp_path, monkeypatch, bad_stats):
    city_dir = tmp_path / "ornek"
    city_dir.mkdir()
    (city_dir / "stats.json").write_text(bad_stats, encoding="utf-8")
    existing_index = tmp_path / "index.html"
    existing_index.write_text("previous index", encoding="utf-8")
    monkeypatch.setattr(build_docs_index, "DOCS_DIR", tmp_path)

    with pytest.raises(SystemExit, match="stats.json"):
        build_docs_index.build_index()

    assert existing_index.read_text(encoding="utf-8") == "previous index"
