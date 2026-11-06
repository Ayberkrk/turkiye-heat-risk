"""Uçtan uca regresyon testi: Landsat, OSM, nüfus, HVI, harita, belirsizlik, veri paketi.

Birim testler her modülü ayrı ayrı sentetik veriyle dener; bu test ise
`pipeline.py`'yi gerçek veriden kesilmiş küçük bir şehirle (tests/fixtures/ornek,
bkz. tools/build_e2e_fixture.py) baştan sona çalıştırır. Pipeline ayrı bir
süreçte, kodun geçici bir kopyasında ve erişilemez bir vekil sunucuyla
(HTTP(S)_PROXY) koşar: herhangi bir ağ isteği hata verir, yani test hattın
gerçekten çevrimdışı çalıştığını da kanıtlar.

Beklenen değerler `tests/fixtures/ornek/beklenen.json`'da. Formül bilerek
değiştiğinde güncellemek için:

    REGENERATE_E2E=1 pytest tests/test_e2e.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest

from tools.run_demo import prepare_workspace

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "ornek"
EXPECTED = FIXTURE / "beklenen.json"
CITY = "ornek"


@pytest.fixture(scope="module")
def e2e_run(tmp_path_factory):
    work = prepare_workspace(tmp_path_factory.mktemp("e2e") / "calisma")
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
           "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "NO_PROXY": "",
           "MPLBACKEND": "Agg"}
    result = subprocess.run(
        [sys.executable, "pipeline.py", "--city", CITY, "--years", "2020", "2026", "--main-year", "2026",
         "--uncertainty-runs", "60"],
        cwd=work, env=env, capture_output=True, text=True, timeout=900, check=False,
    )
    return work, result


def _observed(work: Path) -> dict:
    roads = gpd.read_file(work / "data" / "processed" / CITY / "roads_with_hvi.geojson", ignore_geometry=True)
    scored = roads["hvi_score_2026"].notna()
    top = (roads[scored].groupby("mahalle_adi")["hvi_percentage_2026"].mean().sort_values(ascending=False))
    return {
        "road_count": int(len(roads)),
        "scored_roads": int(scored.sum()),
        "mean_lst_2020": round(float(roads["lst_mean_2020"].mean()), 3),
        "mean_lst_2026": round(float(roads["lst_mean_2026"].mean()), 3),
        "mean_hvi_score_2026": round(float(roads.loc[scored, "hvi_score_2026"].mean()), 3),
        "category_counts_2026": {k: int(v) for k, v in roads.loc[scored, "hvi_category_2026"].value_counts().items()},
        "top_mahalle_2026": top.index[0],
    }


def test_pipeline_runs_offline_end_to_end(e2e_run):
    work, result = e2e_run
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    proc, out = work / "data" / "processed" / CITY, work / "output" / CITY
    for path in (proc / "roads_with_hvi.geojson", proc / "nufus_izgarasi_kalibrasyon.csv",
                 proc / "uncertainty" / "belirsizlik_ozet.json", work / "docs" / CITY / "index.html",
                 work / "docs" / CITY / "manifest.json", out / "paket" / "ozet.html",
                 work / "output" / CITY / f"{CITY}_veri_paketi.zip"):
        assert path.exists(), path
    summary = json.loads((proc / "uncertainty" / "belirsizlik_ozet.json").read_text(encoding="utf-8"))
    assert summary["default_run_reproduces_published_index_pearson"] == pytest.approx(1.0, abs=1e-6)
    with zipfile.ZipFile(work / "output" / CITY / f"{CITY}_veri_paketi.zip") as archive:
        names = {Path(n).name for n in archive.namelist()}
    assert {f"{CITY}_isi_riski.xlsx", f"{CITY}_isi_riski.gpkg", "harita.png"} <= names


def test_pipeline_output_matches_the_recorded_regression_values(e2e_run):
    work, result = e2e_run
    assert result.returncode == 0
    observed = _observed(work)
    if os.environ.get("REGENERATE_E2E"):
        EXPECTED.write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pytest.skip("beklenen.json yeniden üretildi")
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert observed["road_count"] == expected["road_count"]
    assert observed["scored_roads"] == expected["scored_roads"]
    for key in ("mean_lst_2020", "mean_lst_2026", "mean_hvi_score_2026"):
        assert observed[key] == pytest.approx(expected[key], abs=0.05), key
    # GDAL/GEOS sürüm farkları sınırdaki birkaç yolun kategorisini oynatabilir.
    for category, count in expected["category_counts_2026"].items():
        assert abs(observed["category_counts_2026"].get(category, 0) - count) <= 3, category
    assert observed["top_mahalle_2026"] == expected["top_mahalle_2026"]
