"""Bursa district-level ADNKS and SEGE reference tables.

Age-group counts: 2023 Bursa İŞKUR activity report, Table 1
(https://media.iskur.gov.tr/94382/bursa.pdf). SEGE ranks/scores:
T.C. Sanayi ve Teknoloji Bakanlığı SEGE-2022 report.
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
    """Data are versioned in the repository; no download is required."""
    return {}


def build_neighborhood_layer(pbf_path: Path, population_paths: dict[str, Path], config: CityConfig) -> gpd.GeoDataFrame:
    return build_neighborhood_layer_from_ilce_tables(pbf_path, config, ILCE_NUFUS_CSV_PATH, SEGE_CSV_PATH)
