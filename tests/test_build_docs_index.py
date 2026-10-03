import json

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
    # kalan harita (ya da manifest'ten önce üretilmiş olan) sayfada
    # işaretlenmeli; aksi halde farklı formüllerin sayıları yan yana durur.
    _write_city(tmp_path, "guncel", "Güncel Şehir", HVI_FORMULA_VERSION)
    _write_city(tmp_path, "eski", "Eski Şehir", HVI_FORMULA_VERSION - 1)
    _write_city(tmp_path, "manifestsiz", "Manifestsiz Şehir")
    monkeypatch.setattr(build_docs_index, "DOCS_DIR", tmp_path)

    html = build_docs_index.build_index().read_text(encoding="utf-8")

    assert html.count("Eski formülle üretildi") == 2
    # Güncel şehir önce listelenir ve işaret taşımaz.
    guncel, eski = html.index("Güncel Şehir"), html.index("Eski Şehir")
    assert guncel < eski
    assert "Eski formülle üretildi" not in html[guncel:eski]
