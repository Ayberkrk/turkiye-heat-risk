"""Ana pipeline çıktısı üzerinde üç kontrol: istasyon karşılaştırması, tampon
duyarlılığı ve 2020-2026 değişiminin ayrıştırılması.

    python pipeline.py --city izmir --years 2020 2026 --main-year 2026
    python validation_analysis.py --city izmir

Uydu verisi indirmez (pipeline'ın sahne ve mozaiklerini okur); istasyon
karşılaştırması NOAA GHCNh saatlik kayıtlarını indirir ve önbelleğe alır.
Yöntem ve sınırlar: src/core/station_check.py ve src/core/sensitivity.py.
Çıktılar `data/processed/<şehir>/validation/` altına yazılır.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import geopandas as gpd  # noqa: E402

from core.city_config import load_city_config  # noqa: E402
from core.paths import city_data_proc  # noqa: E402
from core.sensitivity import (  # noqa: E402
    DEFAULT_BUFFERS_M,
    buffer_sensitivity,
    temporal_decomposition,
    write_sensitivity_outputs,
)
from core.station_check import run_station_check  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", default="izmir", help="src/cities/<şehir>/config.yaml içindeki şehir kimliği")
    parser.add_argument("--main-year", help="pipeline.py'deki referans yıl; varsayılan en yeni yıl")
    parser.add_argument("--buffers", nargs="+", type=int, default=list(DEFAULT_BUFFERS_M),
                        help="Karşılaştırılacak yol tamponları, metre (ilki referans)")
    parser.add_argument("--skip-stations", action="store_true", help="İstasyon karşılaştırmasını atla (ağ gerekmez)")
    args = parser.parse_args()

    config = load_city_config(args.city)
    roads_path = city_data_proc(config.city_id) / "roads_with_hvi.geojson"
    if not roads_path.exists():
        parser.error(f"{roads_path} yok. Önce `pipeline.py --city {args.city}` çalıştırın.")
    roads = gpd.read_file(roads_path)
    years = sorted({m.group(1) for c in roads.columns if (m := re.fullmatch(r"hvi_score_(\d{4})", c))}, key=int)
    main_year = args.main_year or years[-1]

    if not args.skip_stations:
        out = run_station_check(config, years, main_year)
        station = json.loads((out / "istasyon_ozet.json").read_text(encoding="utf-8"))
        print(f"İstasyon: {station['pairs']} sahne-istasyon çifti, gün içi anomali korelasyonu "
              f"{station.get('pearson_within_station_anomalies')}")
    print("Tampon duyarlılığı...")
    buffers = buffer_sensitivity(config, roads, years, main_year, tuple(sorted(args.buffers)))
    print(buffers["summary"].to_string(index=False))
    temporal = temporal_decomposition(roads, years) if len(years) > 1 else None
    if temporal:
        print(json.dumps(temporal["summary"], ensure_ascii=False, indent=1))
    out = write_sensitivity_outputs(config, roads, buffers, temporal)
    print(f"Tablolar: {out}")


if __name__ == "__main__":
    main()
