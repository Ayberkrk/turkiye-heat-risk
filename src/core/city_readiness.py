"""Offline structural checks for the configured city registry.

These checks establish that city configuration and bundled table inputs are
well-formed. They do not verify that a statistic matches its cited source or
that OSM coverage is sufficient; those require external source evidence and,
for OSM coverage, the city's extract.
"""

from __future__ import annotations

import importlib
import inspect
import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pyproj
import yaml

from core.city_config import CITIES_DIR, validate_config_dict
from core.hvi import HVI_FORMULA_VERSION
from core.text_utils import normalize_name

_POPULATION_COLUMNS = {"ILCE", "NUFUS", "YASLI_ORAN", "COCUK_ORAN"}
_SEGE_COLUMNS = {"ILCE", "SKOR"}
_CITY_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _table_errors(path: Path, required: set[str], city_id: str, table_name: str) -> tuple[list[str], pd.DataFrame | None]:
    errors: list[str] = []
    if not path.is_file():
        return [f"{city_id}: {table_name} dosyası yok: {path.name}"], None
    try:
        table = pd.read_csv(path, sep=";", encoding="utf-8", dtype={"ILCE": "string"})
    except (OSError, UnicodeError, pd.errors.ParserError, ValueError) as error:
        return [f"{city_id}: {table_name} okunamadı: {error}"], None
    missing = sorted(required - set(table.columns))
    if missing:
        return [f"{city_id}: {table_name} eksik sütun içeriyor: {', '.join(missing)}"], table
    if table.empty:
        errors.append(f"{city_id}: {table_name} boş")
    names = table["ILCE"].fillna("").astype(str).str.strip()
    if names.eq("").any():
        errors.append(f"{city_id}: {table_name} boş ilçe adı içeriyor")
    normalized = names.map(normalize_name)
    if normalized.eq("").any():
        errors.append(f"{city_id}: {table_name} normalize edilemeyen ilçe adı içeriyor")
    if normalized.duplicated().any():
        repeated = sorted(normalized[normalized.duplicated(keep=False)].unique())
        errors.append(f"{city_id}: {table_name} normalize edilmiş ilçe anahtarları tekrarlı: {repeated}")
    return errors, table


def _finite_numeric(table: pd.DataFrame, column: str, city_id: str, table_name: str) -> tuple[list[str], pd.Series]:
    values = pd.to_numeric(table[column], errors="coerce")
    invalid = values.isna() | ~np.isfinite(values.to_numpy(dtype=float, na_value=np.nan))
    errors = []
    if invalid.any():
        errors.append(f"{city_id}: {table_name}.{column} sayısal olmayan, eksik veya sonsuz değer içeriyor")
    return errors, values


def _csv_data_errors(city_id: str, city_dir: Path, adapter_path: str) -> list[str]:
    """Check bundled city tables without downloading or interpreting source claims."""
    errors: list[str] = []
    try:
        adapter = importlib.import_module(adapter_path)
    except ImportError:
        return []  # Import failure is already reported by _city_static_errors.
    uses_ilce_tables = callable(getattr(adapter, "build_neighborhood_layer_from_ilce_tables", None))
    sege_path = city_dir / "sege_2022_ilce.csv"
    sege = None
    if uses_ilce_tables or sege_path.exists():
        sege_errors, sege = _table_errors(sege_path, _SEGE_COLUMNS, city_id, "SEGE tablosu")
        errors.extend(sege_errors)
    if sege is not None and _SEGE_COLUMNS.issubset(sege.columns):
        score_errors, _ = _finite_numeric(sege, "SKOR", city_id, "SEGE tablosu")
        errors.extend(score_errors)

    # İzmir obtains population and age data from a configured CKAN source.
    # Other registered cities use the local TÜİK/SEGE table adapter. Future
    # adapters may use different sources and are not forced into this schema.
    if not uses_ilce_tables:
        return errors

    population_errors, population = _table_errors(
        city_dir / "ilce_nufus.csv", _POPULATION_COLUMNS, city_id, "Nüfus tablosu"
    )
    errors.extend(population_errors)
    if population is None or not _POPULATION_COLUMNS.issubset(population.columns):
        return errors

    numeric: dict[str, pd.Series] = {}
    for column in ("NUFUS", "YASLI_ORAN", "COCUK_ORAN"):
        column_errors, values = _finite_numeric(population, column, city_id, "Nüfus tablosu")
        errors.extend(column_errors)
        numeric[column] = values
    if (numeric["NUFUS"] <= 0).any():
        errors.append(f"{city_id}: Nüfus tablosunda pozitif olmayan nüfus değeri var")
    for column in ("YASLI_ORAN", "COCUK_ORAN"):
        if ((numeric[column] < 0) | (numeric[column] > 1)).any():
            errors.append(f"{city_id}: Nüfus tablosundaki {column} oranı [0, 1] dışında")
    if (numeric["YASLI_ORAN"] + numeric["COCUK_ORAN"] > 1 + 1e-9).any():
        errors.append(f"{city_id}: Yaşlı ve çocuk oranları toplamı 1'i aşıyor")

    if sege is not None and _SEGE_COLUMNS.issubset(sege.columns):
        population_keys = set(population["ILCE"].fillna("").astype(str).map(normalize_name))
        sege_keys = set(sege["ILCE"].fillna("").astype(str).map(normalize_name))
        missing_sege = sorted(population_keys - sege_keys)
        if missing_sege:
            errors.append(f"{city_id}: Nüfus tablosundaki ilçeler SEGE tablosunda yok: {missing_sege}")
    return errors


def _city_static_errors(city_id: str, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    city = config.get("city", {})
    osm = config.get("osm", {})
    roads = config.get("roads", {})
    population = config.get("population", {})
    if not isinstance(city.get("name"), str) or not city["name"].strip():
        errors.append(f"{city_id}: city.name boş olamaz")
    attribution = city.get("attribution")
    if not isinstance(attribution, str) or not attribution.strip():
        errors.append(f"{city_id}: city.attribution kaynak künyesi eksik")

    try:
        crs = pyproj.CRS(city.get("crs"))
        if not crs.is_projected:
            errors.append(f"{city_id}: city.crs metre tabanlı projeksiyon olmalı; {crs.to_string()} coğrafi")
        elif any((axis.unit_name or "").lower() not in {"metre", "meter", "metres", "meters"}
                 or not math.isclose(axis.unit_conversion_factor, 1.0, rel_tol=0, abs_tol=1e-12)
                 for axis in crs.axis_info[:2]):
            errors.append(f"{city_id}: city.crs mesafe/alan hesapları için metre biriminde olmalı")
    except (pyproj.exceptions.CRSError, TypeError, ValueError):
        pass  # validate_config_dict already reports invalid CRS definitions.

    pbf_url = osm.get("pbf_url")
    parsed_url = urlparse(pbf_url) if isinstance(pbf_url, str) else None
    if not parsed_url or parsed_url.scheme != "https" or not parsed_url.netloc:
        errors.append(f"{city_id}: osm.pbf_url geçerli bir HTTPS URL olmalı")
    highway_types = osm.get("highway_types")
    if (not isinstance(highway_types, list) or not highway_types
            or any(not isinstance(item, str) or not item.strip() for item in highway_types)):
        errors.append(f"{city_id}: osm.highway_types boş olmayan metin listesi olmalı")
    elif len(highway_types) != len(set(highway_types)):
        errors.append(f"{city_id}: osm.highway_types yinelenen tür içeriyor")
    for key in ("admin_level_ilce", "admin_level_mahalle"):
        value = osm.get(key)
        if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 12:
            errors.append(f"{city_id}: osm.{key} 1-12 arası idari seviye olmalı")
    buffer_m = roads.get("buffer_meters", 10)
    if isinstance(buffer_m, bool) or not isinstance(buffer_m, (int, float)) or not math.isfinite(buffer_m) or buffer_m <= 0:
        errors.append(f"{city_id}: roads.buffer_meters pozitif ve sonlu olmalı")

    adapter_path = population.get("adapter")
    if not isinstance(adapter_path, str) or not adapter_path.strip():
        errors.append(f"{city_id}: population.adapter eksik")
    elif not _CITY_ID_RE.fullmatch(city_id) or adapter_path != f"cities.{city_id}.adapter":
        errors.append(f"{city_id}: population.adapter şehir modülüyle eşleşmiyor: {adapter_path}")
    else:
        try:
            adapter = importlib.import_module(adapter_path)
            expected_parameters = {"fetch_population_data": 1, "build_neighborhood_layer": 3}
            for function_name, expected in expected_parameters.items():
                function = getattr(adapter, function_name, None)
                if not callable(function):
                    errors.append(f"{city_id}: adapter {function_name}() sağlamıyor")
                    continue
                try:
                    signature = inspect.signature(function)
                    positional = [parameter for parameter in signature.parameters.values()
                                  if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                                        inspect.Parameter.POSITIONAL_OR_KEYWORD)]
                    required = [parameter for parameter in positional
                                if parameter.default is inspect.Parameter.empty]
                    has_varargs = any(parameter.kind is inspect.Parameter.VAR_POSITIONAL
                                      for parameter in signature.parameters.values())
                    if not has_varargs and (len(required) > expected or len(positional) < expected):
                        errors.append(f"{city_id}: adapter {function_name}() {expected} pozisyonel argüman kabul etmeli")
                except (TypeError, ValueError):
                    errors.append(f"{city_id}: adapter {function_name}() imzası incelenemedi")
        except (ImportError, AttributeError) as error:
            errors.append(f"{city_id}: adapter import edilemiyor: {error}")

    if adapter_path == "cities.izmir.adapter":
        base = population.get("ckan_base")
        datasets = population.get("datasets")
        if not isinstance(base, str) or urlparse(base).scheme != "https" or not urlparse(base).netloc:
            errors.append(f"{city_id}: population.ckan_base geçerli HTTPS URL olmalı")
        if not isinstance(datasets, dict) or not datasets or any(
                not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
                for key, value in (datasets.items() if isinstance(datasets, dict) else [])):
            errors.append(f"{city_id}: population.datasets boş olmayan ad/ID eşlemesi olmalı")
    return errors


def _published_status(city_id: str, docs_dir: Path) -> str:
    city_docs = docs_dir / city_id
    if not (city_docs / "index.html").is_file():
        return "not_published"
    manifest_path = city_docs / "manifest.json"
    if not manifest_path.is_file():
        return "unversioned"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = manifest.get("versions", {}).get("hvi_formula_version")
    except (OSError, json.JSONDecodeError, AttributeError):
        return "invalid_manifest"
    if version is None:
        return "unversioned"
    return "current" if version == HVI_FORMULA_VERSION else "stale"


def validate_city_readiness(city_id: str, cities_dir: Path = CITIES_DIR,
                            docs_dir: Path | None = None) -> dict[str, Any]:
    """Return an offline readiness report for one registered city."""
    city_dir = cities_dir / city_id
    config_path = city_dir / "config.yaml"
    report: dict[str, Any] = {
        "city_id": city_id,
        "config_valid": False,
        "adapter_valid": False,
        "bundled_data_valid": False,
        "source_attribution": "not_checked",
        "osm_coverage": "not_measured",
        "source_values": "not_independently_verified",
        "published_map": _published_status(city_id, docs_dir) if docs_dir else "not_checked",
        "errors": [],
    }
    errors: list[str] = []
    if not _CITY_ID_RE.fullmatch(city_id):
        report["errors"] = [f"Geçersiz şehir kimliği: {city_id!r}"]
        return report
    if not config_path.is_file():
        report["errors"] = [f"{city_id}: config.yaml bulunamadı"]
        return report
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        report["errors"] = [f"{city_id}: config.yaml okunamadı: {error}"]
        return report
    errors.extend(validate_config_dict(config))
    if errors:
        report["errors"] = errors
        return report
    report["config_valid"] = True
    errors.extend(_city_static_errors(city_id, config))
    report["adapter_valid"] = not any("adapter" in error for error in errors)
    attribution = config.get("city", {}).get("attribution")
    report["source_attribution"] = "present_not_verified" if isinstance(attribution, str) and attribution.strip() else "missing"
    errors.extend(_csv_data_errors(city_id, city_dir, config.get("population", {}).get("adapter", "")))
    report["bundled_data_valid"] = not any(
        "tablosu" in error or "tablosundaki" in error or "CSV" in error for error in errors
    )
    report["errors"] = errors
    return report


def validate_city_registry(cities_dir: Path = CITIES_DIR, docs_dir: Path | None = None) -> dict[str, Any]:
    """Validate every city config and bundled table, with published-map status."""
    city_ids = sorted(path.parent.name for path in cities_dir.glob("*/config.yaml"))
    reports = [validate_city_readiness(city_id, cities_dir, docs_dir) for city_id in city_ids]
    return {
        "configured_city_count": len(city_ids),
        "structurally_valid_count": sum(not report["errors"] for report in reports),
        "published_current_count": sum(report["published_map"] == "current" for report in reports),
        "published_stale_count": sum(report["published_map"] == "stale" for report in reports),
        "published_unversioned_count": sum(report["published_map"] == "unversioned" for report in reports),
        "not_published_count": sum(report["published_map"] == "not_published" for report in reports),
        "source_values_independently_verified": 0,
        "osm_coverages_measured": 0,
        "cities": reports,
    }
