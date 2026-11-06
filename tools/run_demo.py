"""İnternet ve veri indirmesi olmadan, bir dakikadan kısa sürede çalışan demo.

Gerçek veriden kesilmiş küçük örnek şehri (tests/fixtures/ornek, ~1,7 km,
604 yol) kodun geçici bir kopyasında baştan sona çalıştırır: Landsat
mozaiği, OSM yol ağı, nüfus ızgarası, HVI, harita, belirsizlik analizi ve
veri paketi. Depodaki data/, docs/ ve output/ klasörlerine dokunmaz.

    python tools/run_demo.py            # çıktılar output/demo/ altında
    python tools/run_demo.py --open     # haritayı ve özeti tarayıcıda aç

Katkıcılar için: bir değişikliğin hattı bozup bozmadığını gerçek şehri
saatlerce indirmeden görmenin en hızlı yolu budur. Aynı kurulum
tests/test_e2e.py'de regresyon testi olarak çalışır.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "ornek"
CITY = "ornek"


def prepare_workspace(work: Path) -> Path:
    """Kodu ve örnek şehri `work` altına kurar; pipeline'ın çalışacağı klasörü döndürür."""
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copytree(ROOT / "src", work / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pipeline.py", "CITATION.cff"):
        shutil.copy2(ROOT / name, work / name)
    city_dir = work / "src" / "cities" / CITY
    city_dir.mkdir()
    for item in FIXTURE.iterdir():
        if item.name in ("raw", "beklenen.json"):
            continue
        (shutil.copytree if item.is_dir() else shutil.copy2)(item, city_dir / item.name)
    shutil.copytree(FIXTURE / "raw", work / "data" / "raw" / CITY)
    return work


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "demo", help="Çalışma klasörü")
    parser.add_argument("--open", action="store_true", help="Haritayı ve özet raporu tarayıcıda aç")
    args = parser.parse_args()

    work = prepare_workspace(args.out.resolve())
    subprocess.run([sys.executable, "pipeline.py", "--city", CITY, "--years", "2020", "2026",
                    "--main-year", "2026", "--uncertainty-runs", "100"], cwd=work, check=True)
    report = work / "output" / CITY / "paket" / "ozet.html"
    print(f"\nDemo tamam. Harita: {work / 'output' / f'{CITY}_hvi_map.html'}\nÖzet: {report}")
    if args.open:
        webbrowser.open((work / "output" / f"{CITY}_hvi_map.html").as_uri())
        webbrowser.open(report.as_uri())


if __name__ == "__main__":
    main()
