"""Bir şehrin veri paketini (Excel, CSV, GeoPackage, görseller, özet) yeniden üretir.

`pipeline.py` paketi zaten son adımda yazar; bu komut yalnızca paketi,
pipeline'ı baştan çalıştırmadan tazelemek içindir (ör. belirsizlik analizi
farklı ayarlarla yeniden koşulduktan sonra). Örnek:

    python export_city.py --city izmir

Çıktılar: `output/<şehir>/<şehir>_veri_paketi.zip` ve sitede sunulan küçük
kopyalar için `docs/<şehir>/indir/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.city_config import load_city_config  # noqa: E402
from core.export import export_city_package  # noqa: E402
from core.paths import city_data_proc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", nargs="+", default=["izmir"], help="Bir ya da daha fazla şehir kimliği")
    parser.add_argument("--no-polygons", action="store_true", help="GeoPackage'a mahalle poligonlarını ekleme")
    args = parser.parse_args()

    for city_id in args.city:
        config = load_city_config(city_id)
        if not (city_data_proc(city_id) / "roads_with_hvi.geojson").exists():
            print(f"{city_id}: roads_with_hvi.geojson yok, önce pipeline.py çalıştırılmalı; atlanıyor")
            continue
        export_city_package(config, include_polygons=not args.no_polygons)


if __name__ == "__main__":
    main()
