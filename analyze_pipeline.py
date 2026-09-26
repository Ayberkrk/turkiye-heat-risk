"""Create a multi-year weather-adjusted and intervention analysis package.

The regular pipeline must already have rasters and HVI road data for each
requested year. For example:

    python pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
    python analyze_pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.city_config import load_city_config  # noqa: E402
from core.impact_analysis import run_impact_analysis  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", default="izmir", help="src/cities/<şehir>/config.yaml içindeki şehir kimliği")
    parser.add_argument("--years", nargs="+", required=True, help="Raster/HVI çıktıları hazır yıllar; en az üç farklı yıl")
    parser.add_argument("--main-year", help="pipeline.py çalışırken kullanılan referans yıl; varsayılan en yeni analiz yılı")
    parser.add_argument("--buffers", nargs="+", type=int, help="Duyarlılık analizindeki LST/NDVI yol tamponları (metre)")
    parser.add_argument("--cooling-c", type=float, default=2.0, help="Gölgeleme senaryosunun varsayımsal LST düşüşü, °C (varsayılan 2)")
    parser.add_argument("--ndvi-delta", type=float, default=0.15, help="Ağaç örtüsü senaryosunun varsayımsal NDVI artışı (varsayılan 0.15)")
    parser.add_argument("--target-share", type=float, default=0.20, help="Senaryonun uygulanacağı en yüksek riskli yol payı (varsayılan 0.20)")
    parser.add_argument("--weather-beta", type=float, default=1.0, help="ERA5-Land hava anomalisi düzeltme katsayısı; beta duyarlılığı da rapora yazılır")
    parser.add_argument("--refresh-weather", action="store_true", help="Önbellekteki ERA5-Land yanıtını yeniden indir")
    args = parser.parse_args()

    years = sorted(set(args.years), key=int)
    main_year = args.main_year or years[-1]
    if main_year not in years:
        parser.error("--main-year, --years listesinde olmalı.")
    config = load_city_config(args.city)
    output_dir = run_impact_analysis(
        config,
        years,
        main_year,
        buffers_m=args.buffers,
        cooling_c=args.cooling_c,
        ndvi_delta=args.ndvi_delta,
        target_share=args.target_share,
        weather_beta=args.weather_beta,
        refresh_weather=args.refresh_weather,
    )
    print(f"Harita ve tablolar: {output_dir}")


if __name__ == "__main__":
    main()
