"""Uçtan uca test ve demo için küçük, gerçek bir örnek şehir üretir (`tests/fixtures/ornek/`).

İzmir'in Karabağlar/Konak sınırında ~1,7 x 1,7 km'lik bir alanın gerçek
verisinden kesilir: her yıl için bir Landsat sahnesinin dört bandı (şehir
penceresi), OSM yol/bina/sağlık/yeşil alan/idari sınır katmanları, İzmir
açık veri portalının nüfus tabloları ve HRSL nüfus ızgarası. Sonuç birkaç MB
tutar ve pipeline'ı ağ bağlantısı olmadan baştan sona çalıştırır
(bkz. tests/test_e2e.py, tools/run_demo.py).

Yeniden üretmek için önce İzmir'in tam pipeline'ı çalışmış olmalı:

    python pipeline.py --city izmir --years 2020 2026 --main-year 2026
    python tools/build_e2e_fixture.py

Lisans: OSM katmanları © OpenStreetMap katkıcıları (ODbL 1.0), Landsat
USGS (kamu malı), HRSL Meta & CIESIN (CC BY 4.0), nüfus İzmir B.Ş.B. açık veri.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.paths import city_data_raw, year_paths  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "ornek"
BBOX = [27.10, 38.39, 27.12, 38.405]
YEARS = ["2020", "2026"]
MAIN_YEAR = "2026"
WINDOW_MARGIN_M = 2500.0  # satellite.WINDOW_MARGIN_M (2 km) + pay
BANDS = {"red": "band4_red.tif", "nir08": "band5_nir.tif", "lwir11": "band10_thermal.tif",
         "qa_pixel": "band_qa_pixel.tif"}
# Testte kullanılan OSM sütunları; geri kalanlar yalnızca boyut ekler.
OSM_COLUMNS = {
    "lines": ["osm_id", "name", "highway", "other_tags"],
    "multipolygons": ["osm_id", "osm_way_id", "name", "type", "amenity", "admin_level", "boundary", "building",
                      "landuse", "leisure", "natural", "other_tags"],
    "points": ["osm_id", "name", "highway", "other_tags"],
}


def _crop(src_path: Path, dst_path: Path, bbox: list[float], margin_m: float) -> bool:
    with rasterio.open(src_path) as src:
        west, south, east, north = transform_bounds("EPSG:4326", src.crs, *bbox)
        window = from_bounds(west - margin_m, south - margin_m, east + margin_m, north + margin_m, src.transform)
        window = window.round_offsets(op="floor").round_lengths(op="ceil").intersection(
            Window(0, 0, src.width, src.height))
        data = src.read(1, window=window)
        profile = src.profile.copy()
        profile.update(width=window.width, height=window.height, transform=src.window_transform(window),
                       compress="deflate", tiled=False)
        for key in ("blockxsize", "blockysize", "photometric", "interleave"):
            profile.pop(key, None)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data, 1)
    return True


def _scene_covers(scene_dir: Path) -> float:
    """Sahnenin bbox içindeki bulutsuz piksel oranı."""
    from core.raster import qa_invalid_mask

    with rasterio.open(scene_dir / "band_qa_pixel.tif") as src:
        window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *BBOX), src.transform)
        window = window.round_offsets().round_lengths()
        if window.col_off < 0 or window.row_off < 0 or window.col_off + window.width > src.width \
                or window.row_off + window.height > src.height:
            return 0.0
        return float((~qa_invalid_mask(src.read(1, window=window))).mean())


def build() -> None:
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    (FIXTURE / "raw" / "population").mkdir(parents=True)

    features = []
    for year in YEARS:
        raw_dir, _ = year_paths("izmir", year, MAIN_YEAR)
        metadata = json.loads((raw_dir / "scene_metadata.json").read_text(encoding="utf-8"))
        scenes = sorted(metadata["scenes"], key=lambda s: -_scene_covers(raw_dir / s["folder"]))
        scene = scenes[0]
        print(f"{year}: {scene['scene_id']} (bbox bulutsuz oranı %{_scene_covers(raw_dir / scene['folder']) * 100:.0f})")
        assets = {}
        for asset, filename in BANDS.items():
            relative = Path("landsat") / scene["scene_id"] / filename
            _crop(raw_dir / scene["folder"] / filename, FIXTURE / relative, BBOX, WINDOW_MARGIN_M)
            assets[asset] = {"href": str(relative), "type": "image/tiff; application=geotiff"}
        with rasterio.open(FIXTURE / "landsat" / scene["scene_id"] / "band10_thermal.tif") as src:
            item_bbox = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
        path, row = scene["tile"].split("_")
        features.append({
            "type": "Feature", "stac_version": "1.0.0", "id": scene["scene_id"],
            "bbox": item_bbox,
            "geometry": {"type": "Polygon", "coordinates": [[
                [item_bbox[0], item_bbox[1]], [item_bbox[2], item_bbox[1]], [item_bbox[2], item_bbox[3]],
                [item_bbox[0], item_bbox[3]], [item_bbox[0], item_bbox[1]]]]},
            "properties": {"datetime": f"{scene['date']}T08:40:00Z", "eo:cloud_cover": scene["cloud_cover"],
                           "platform": scene["platform"], "landsat:wrs_path": int(path), "landsat:wrs_row": int(row)},
            "assets": assets, "links": [],
        })
    (FIXTURE / "sahneler.json").write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")

    pbf = FIXTURE / "raw" / "ornek.osm.pbf"  # içerik GeoPackage; GDAL biçimi içerikten tanır
    izmir_pbf = city_data_raw("izmir") / "izmir.osm.pbf"
    for layer, columns in OSM_COLUMNS.items():
        frame = gpd.read_file(izmir_pbf, layer=layer, bbox=tuple(BBOX))
        frame = frame[[c for c in columns if c in frame.columns] + ["geometry"]]
        if layer == "multipolygons":
            frame = frame[frame[["amenity", "admin_level", "building", "landuse", "leisure", "natural"]].notna().any(axis=1)]
        frame.to_file(pbf, layer=layer, driver="GPKG")

    for name in ("mahalle_nufus.csv", "yas_grubu.csv"):
        shutil.copy2(city_data_raw("izmir") / "population" / name, FIXTURE / "raw" / "population" / name)
    _crop(city_data_raw("izmir") / "population_grid.tif", FIXTURE / "nufus_izgarasi.tif", BBOX, 3000.0)

    izmir_config = (ROOT / "src" / "cities" / "izmir" / "config.yaml").read_text(encoding="utf-8")
    datasets = izmir_config.split("datasets:", 1)[1]
    config = f"""# Uçtan uca test ve demo için örnek şehir (tools/build_e2e_fixture.py üretir).
# İzmir'in Karabağlar/Konak sınırında ~1,7 x 1,7 km. Ağ gerektirmez: Landsat
# sahneleri sahneler.json'dan, OSM ve nüfus raw/ altından, nüfus ızgarası
# nufus_izgarasi.tif'ten okunur.
city:
  name: "Örnek (İzmir, Karabağlar)"
  bbox: {BBOX}
  crs: "EPSG:32635"
  attribution: "Nüfus: İzmir B.Ş.B. Açık Veri Portalı, TÜİK."

landsat:
  max_cloud_cover: 30
  max_scenes_per_tile: 1
  catalog: "sahneler.json"

osm:
  pbf_url: "https://download.openstreetmap.fr/extracts/europe/turkey/aegean-latest.osm.pbf"
  admin_level_ilce: 6
  admin_level_mahalle: 8
  highway_types: [primary, secondary, tertiary, residential, living_street, unclassified]

roads:
  buffer_meters: 10

population_grid:
  url: "src/cities/ornek/nufus_izgarasi.tif"

population:
  adapter: "cities.izmir.adapter"
  ckan_base: "https://acikveri.bizizmir.com"
  datasets:{datasets}"""
    (FIXTURE / "config.yaml").write_text(config, encoding="utf-8")
    size = sum(p.stat().st_size for p in FIXTURE.rglob("*") if p.is_file())
    print(f"Örnek şehir: {FIXTURE} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    build()
