"""Manisa Yunusemre district-level age shares and SEGE-2022 reference data.

Age-group counts: TÜİK ADNKS 2025, as exposed by the DrDataStats district
age-group explorer (https://www.drdatastats.com/yillara-gore-turkiyede-cinsiyet-ve-yas-gruplari-bazinda-ilce-ve-il-nufuslari/).
The 2025 counts for 0–14, 15–64 and 65+ sum to the same explorer's total.
SEGE ranks/scores: T.C. Sanayi ve Teknoloji Bakanlığı, SEGE-2022.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from core.city_config import CityConfig
from core.ilce_table_adapter import build_neighborhood_layer_from_ilce_tables

_CITY_DIR = Path(__file__).resolve().parent
ILCE_NUFUS_CSV_PATH = _CITY_DIR / "ilce_nufus.csv"
SEGE_CSV_PATH = _CITY_DIR / "sege_2022_ilce.csv"


def fetch_population_data(config: CityConfig) -> dict[str, Path]:
    """Veri depoda sürümlü tutulur, indirme gerekmez."""
    return {}


def build_neighborhood_layer(pbf_path: Path, population_paths: dict[str, Path], config: CityConfig) -> gpd.GeoDataFrame:
    return build_neighborhood_layer_from_ilce_tables(pbf_path, config, ILCE_NUFUS_CSV_PATH, SEGE_CSV_PATH)
