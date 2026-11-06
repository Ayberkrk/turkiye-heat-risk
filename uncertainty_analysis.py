"""HVI sıralamasının yöntem kararlarına ne kadar dayanıklı olduğunu ölçer.

Ana pipeline'ın `roads_with_hvi.geojson` çıktısını okur; uydu verisi
indirmez, raster okumaz. Ölçekleme, ağırlık, birleştirme ve bileşen seçimi
kararlarını Monte Carlo ile değiştirip her yol ve mahalle için sıra
aralığını, ilk %10'a girme olasılığını ve kararların birinci derece
duyarlılık indekslerini raporlar (yöntem: src/core/uncertainty.py). Örnek:

    python pipeline.py --city izmir --years 2020 2026 --main-year 2026
    python uncertainty_analysis.py --city izmir --year 2026

Çıktılar `data/processed/<şehir>/uncertainty/` altına yazılır.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import geopandas as gpd  # noqa: E402

from core.city_config import load_city_config  # noqa: E402
from core.paths import city_data_proc  # noqa: E402
from core.uncertainty import UncertaintySettings, run_uncertainty, write_uncertainty_outputs  # noqa: E402


def main() -> None:
    defaults = UncertaintySettings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", default="izmir", help="src/cities/<şehir>/config.yaml içindeki şehir kimliği")
    parser.add_argument("--year", help="Raporlanacak yıl; varsayılan HVI çıktısındaki en yeni yıl")
    parser.add_argument("--runs", type=int, default=defaults.runs, help=f"Monte Carlo koşu sayısı (varsayılan {defaults.runs})")
    parser.add_argument("--seed", type=int, default=defaults.seed, help="Rastgele sayı tohumu (tekrar üretilebilirlik)")
    parser.add_argument("--group-concentration", type=float, default=defaults.group_concentration,
                        help="Grup ağırlıklarının Dirichlet yoğunlaşması; küçük değer = daha geniş ağırlık belirsizliği")
    parser.add_argument("--component-concentration", type=float, default=defaults.component_concentration,
                        help="Grup içi bileşen ağırlıklarının Dirichlet yoğunlaşması")
    parser.add_argument("--exclusion-probability", type=float, default=defaults.exclusion_probability,
                        help="Bir koşuda tek bir bileşenin endeksten çıkarılma olasılığı")
    args = parser.parse_args()

    config = load_city_config(args.city)
    roads_path = city_data_proc(config.city_id) / "roads_with_hvi.geojson"
    if not roads_path.exists():
        parser.error(f"{roads_path} yok. Önce `pipeline.py --city {args.city}` çalıştırın.")
    roads = gpd.read_file(roads_path)
    years = sorted({m.group(1) for c in roads.columns if (m := re.fullmatch(r"hvi_score_(\d{4})", c))}, key=int)
    year = args.year or years[-1]
    if year not in years:
        parser.error(f"--year {year} HVI çıktısında yok; mevcut yıllar: {', '.join(years)}")

    settings = UncertaintySettings(
        runs=args.runs, seed=args.seed, group_concentration=args.group_concentration,
        component_concentration=args.component_concentration, exclusion_probability=args.exclusion_probability,
    )
    result = run_uncertainty(roads, years, year, settings)
    output_dir = write_uncertainty_outputs(config, roads, result)

    summary = result["summary"]
    print(f"{config.name} {year}: {summary['road_count']:,} yol, {settings.runs} koşu")
    print(f"  Varsayılan koşu ile yayımlanan endeks (Pearson): {summary['default_run_reproduces_published_index_pearson']}")
    print(f"  Spearman (varsayılana göre) medyan {summary['spearman_vs_default']['p50']}, "
          f"%5 {summary['spearman_vs_default']['p05']}")
    print(f"  İlk %10 örtüşmesi medyan {summary['top10_overlap_vs_default']['p50']}, "
          f"%5 {summary['top10_overlap_vs_default']['p05']}")
    print(f"  Varsayılan ilk %10'un %{summary['share_of_default_top10_stable_ge_90pct'] * 100:.1f}'i "
          "koşuların en az %90'ında yine ilk %10'da")
    print("  Birinci derece duyarlılık (ilk %10 örtüşmesi):")
    print(result["sensitivity"].to_string())
    print(f"Tablolar: {output_dir}")


if __name__ == "__main__":
    main()
