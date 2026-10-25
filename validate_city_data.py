"""Offline structural quality checks for the configured city registry.

Usage:
    python validate_city_data.py --all
    python validate_city_data.py izmir --json

This command does not download OSM, Landsat, CKAN, or health data. A clean
result means the local config and bundled table structure are usable; it does
not mean source values have been independently verified or OSM coverage has
been measured.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.city_config import CITIES_DIR  # noqa: E402
from core.city_readiness import validate_city_readiness, validate_city_registry  # noqa: E402
from core.paths import DOCS_DIR  # noqa: E402


def _summary(report: dict) -> str:
    return (
        f"Config-valid city definitions: {report['configured_city_count']} | "
        f"structurally valid: {report['structurally_valid_count']} | "
        f"published maps: {report['published_current_count']} current, "
        f"{report['published_unversioned_count']} unversioned, "
        f"{report['published_stale_count']} stale, "
        f"{report['not_published_count']} not published"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", nargs="?", help="src/cities/<city>/config.yaml içindeki kimlik")
    parser.add_argument("--all", action="store_true", help="Tüm şehir kayıtlarını çevrimdışı denetle")
    parser.add_argument("--json", action="store_true", help="Makinece okunabilir JSON raporu yaz")
    args = parser.parse_args()
    if args.all and args.city:
        parser.error("Bir şehir adıyla --all birlikte kullanılamaz.")
    if not args.all and not args.city:
        parser.error("Bir şehir adı ya da --all verilmelidir.")

    if args.all:
        report = validate_city_registry(CITIES_DIR, DOCS_DIR)
        has_errors = report["structurally_valid_count"] != report["configured_city_count"]
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(_summary(report))
            for city in report["cities"]:
                for error in city["errors"]:
                    print(f"ERROR: {error}")
                if city["published_map"] in {"stale", "unversioned", "invalid_manifest"}:
                    print(f"INFO: {city['city_id']}: yayın haritası durumu={city['published_map']}")
            print("Source values independently verified: 0 (not checked by this offline command)")
            print("OSM coverage measurements: 0 (run validate_city.py --osm-coverage with an extract)")
    else:
        report = validate_city_readiness(args.city, CITIES_DIR, DOCS_DIR)
        has_errors = bool(report["errors"])
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"{args.city}: config={report['config_valid']}, adapter={report['adapter_valid']}, "
                  f"bundled_data={report['bundled_data_valid']}, published_map={report['published_map']}")
            print("Source values: not independently verified; OSM coverage: not measured")
            for error in report["errors"]:
                print(f"ERROR: {error}")
    if has_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
