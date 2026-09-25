"""Ordu Altınordu district-level age shares and SEGE-2022 reference data."""

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
