"""Yol ağı ve zaman serisi risk skoru (sıcaklık + ağaç örtüsü).

Şehirden bağımsızdır: OSM pbf URL'i, yol tipleri ve tampon mesafesi
`CityConfig` üzerinden gelir.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import rasterio
import rasterstats
import requests

from core.cache import atomic_output_path, file_signature, is_cache_valid, write_cache_meta
from core.city_config import CityConfig
from core.paths import city_data_proc, city_data_raw, resolve_pbf_path, year_paths

OSM_DOWNLOAD_TIMEOUT_SECONDS = 300

# `compute_road_risk_timeseries` çıktısının formül sürümü - LST/NDVI risk
# skorunun hesaplanma biçimi değiştiğinde artırılmalı (bkz. core/cache.py).
RISK_TIMESERIES_VERSION = 2


def fetch_road_network(config: CityConfig, refresh: bool = False) -> gpd.GeoDataFrame:
    """OSM yol ağını `.osm.pbf` özütünden çeker (Overpass yerine).

    Overpass API büyük bbox'ları onlarca alt sorguya bölüp zaman aşımına
    uğrayabildiği için, bölgesel bir `.pbf` dosyası bir kez indirilip
    yerelden okunuyor - daha öngörülebilir ve hızlı.
    """
    data_raw = city_data_raw(config.city_id)
    data_raw.mkdir(parents=True, exist_ok=True)
    pbf_path = resolve_pbf_path(config.city_id)

    if not pbf_path.exists() or refresh:
        action = "yenileniyor" if pbf_path.exists() else "indiriliyor"
        print(f"{config.name} için OSM özütü {action}: {config.osm_pbf_url}")
        r = requests.get(config.osm_pbf_url, stream=True, timeout=OSM_DOWNLOAD_TIMEOUT_SECONDS)
        r.raise_for_status()
        with atomic_output_path(pbf_path) as temporary:
            with open(temporary, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            if temporary.stat().st_size == 0:
                raise RuntimeError(f"OSM özütü boş indirildi: {config.osm_pbf_url}")

    west, south, east, north = config.bbox
    roads_all = gpd.read_file(pbf_path, layer="lines", bbox=(west, south, east, north))
    roads = roads_all[roads_all["highway"].notna()].copy()
    roads = roads[roads["highway"].isin(config.drive_highway_types)]
    roads = roads[["geometry", "name", "highway"]].reset_index(drop=True)

    roads_utm = roads.to_crs(config.crs)
    roads["length"] = roads_utm.geometry.length
    roads["geometry_buffer"] = roads_utm.geometry.buffer(config.buffer_meters)
    return roads


def compute_road_risk_timeseries(config: CityConfig, years: list[str], main_year: str,
                                  force: bool = False, refresh_osm: bool = False) -> gpd.GeoDataFrame:
    """Her yıl için yol başına ortalama LST ve NDVI'yi hesaplar.

    LST, ortak bir min-max aralığıyla 0-100 risk skoruna çevrilir. Yıllar
    ayrı ayrı normalize edilseydi aynı sıcaklık farklı yıllarda farklı
    skorlara denk gelirdi - karşılaştırmayı anlamsızlaştırırdı. Bu yüzden
    tüm yılların LST değerleri birleştirilip TEK bir ortak ölçekle ölçülüyor.
    (Aynı gerekçe `core/hvi.py` içindeki HVI yüzdesi ve kategori sınırları
    için de geçerlidir; o zincir orada da korunur.)

    NDVI (ağaç örtüsü/bitki örtüsü proxysi) LST ile aynı buffer'dan, aynı
    zonal_stats çağrısıyla çıkarılır - ekstra veri indirmeye gerek yok,
    zaten hesaplanan mozaikten okunuyor.
    """
    if len(years) < 2 or len(set(years)) < 2:
        raise ValueError("Yol zaman serisi için en az iki farklı yıl gerekli.")
    try:
        years = sorted(set(map(str, years)), key=int)
    except ValueError as exc:
        raise ValueError(f"Yıllar tam sayı olmalı: {years}") from exc
    main_year = str(main_year)
    if main_year not in years:
        raise ValueError(f"Referans yıl ({main_year}) seçilen yıllar arasında olmalı: {years}")

    output_path = city_data_proc(config.city_id) / "roads_timeseries.geojson"
    pbf_path = resolve_pbf_path(config.city_id)
    raster_inputs = []
    for year in years:
        _, proc_dir = year_paths(config.city_id, year, main_year)
        raster_inputs.extend([file_signature(proc_dir / "lst_celsius.tif"),
                              file_signature(proc_dir / "ndvi.tif")])
    fingerprint = {
        "city_id": config.city_id,
        "years": years,
        "main_year": main_year,
        "bbox": config.bbox,
        "crs": config.crs,
        "highway_types": config.drive_highway_types,
        "road_buffer_m": config.buffer_meters,
        "osm_pbf_url": config.osm_pbf_url,
        "osm_pbf": file_signature(pbf_path),
        "rasters": raster_inputs,
    }
    if (not refresh_osm and is_cache_valid(
            output_path, RISK_TIMESERIES_VERSION, force=force, fingerprint=fingerprint)):
        print("roads_timeseries.geojson güncel, atlanıyor")
        return gpd.read_file(output_path)

    roads = fetch_road_network(config, refresh=refresh_osm)
    if roads.empty:
        raise ValueError(f"{config.name} bbox'ında seçilen OSM yol türleri bulunamadı.")
    # The PBF may have been downloaded during this run. Persist its actual
    # local signature so a successful first run is reusable on the next one.
    fingerprint["osm_pbf"] = file_signature(pbf_path)
    # LST/NDVI örneklemesi yol yüzeyine yakın kalmalı, bu yüzden dar tampon
    # (`config.buffer_meters`) kullanılır. Bina yoğunluğu için gereken çok
    # daha geniş tampon `core/hvi.py` içinde ayrıca üretilir.
    roads_buffered = gpd.GeoDataFrame(
        roads[["highway"]], geometry=roads["geometry_buffer"], crs=config.crs
    )

    for year in years:
        _, data_proc = year_paths(config.city_id, year, main_year)
        lst_path = data_proc / "lst_celsius.tif"
        ndvi_path = data_proc / "ndvi.tif"
        with rasterio.open(lst_path) as src:
            raster_crs = src.crs.to_epsg()
        roads_for_join = roads_buffered.to_crs(f"EPSG:{raster_crs}")

        lst_stats = rasterstats.zonal_stats(
            roads_for_join, str(lst_path), stats=["mean"], nodata=-9999.0, all_touched=False
        )
        roads[f"lst_mean_{year}"] = [s["mean"] for s in lst_stats]
        print(f"[{year}] {roads[f'lst_mean_{year}'].notna().sum():,} yolda geçerli LST bulundu")

        ndvi_stats = rasterstats.zonal_stats(
            roads_for_join, str(ndvi_path), stats=["mean"], nodata=-9999.0, all_touched=False
        )
        roads[f"ndvi_mean_{year}"] = [s["mean"] for s in ndvi_stats]

    year_columns = [f"lst_mean_{y}" for y in years]
    valid_counts = roads[year_columns].notna().sum()
    has_all_years = roads[year_columns].notna().all(axis=1)
    roads_valid = roads[has_all_years].copy()

    coverage_details = {
        "road_count_total": int(len(roads)),
        "road_count_valid_all_years": int(len(roads_valid)),
        "coverage_all_years_fraction": float(len(roads_valid) / len(roads)),
        "per_year_valid_road_count": {year: int(valid_counts[f"lst_mean_{year}"]) for year in years},
        "years": years,
    }
    print(f"Ortak çok yıllı kapsam: {len(roads_valid):,}/{len(roads):,} yol "
          f"(%{coverage_details['coverage_all_years_fraction'] * 100:.1f}); "
          f"yıl başına geçerli ölçüm: {coverage_details['per_year_valid_road_count']}")
    if roads_valid.empty:
        raise ValueError(
            f"{config.name}: seçilen yılların hiçbirinde ortak LST verisi olan yol yok. "
            f"Yıl başına geçerli ölçüm sayıları: {coverage_details['per_year_valid_road_count']}"
        )

    combined = pd.concat([roads_valid[f"lst_mean_{y}"] for y in years])
    global_min, global_max = combined.min(), combined.max()

    for year in years:
        if global_max == global_min:
            # Sabit ölçüm kümesinde göreli sıralama yoktur; tüm yollar aynı
            # nötr göreli skoru alır, NaN/inf üretilmez.
            roads_valid[f"risk_score_{year}"] = 0.0
        else:
            roads_valid[f"risk_score_{year}"] = (
                (roads_valid[f"lst_mean_{year}"] - global_min) / (global_max - global_min) * 100
            ).round(1)

    first_year, last_year = years[0], years[-1]
    roads_valid["delta_lst"] = (roads_valid[f"lst_mean_{last_year}"] - roads_valid[f"lst_mean_{first_year}"]).round(1)
    roads_valid["delta_risk"] = (roads_valid[f"risk_score_{last_year}"] - roads_valid[f"risk_score_{first_year}"]).round(1)
    roads_valid["degisim_kategori"] = pd.cut(
        roads_valid["delta_lst"], bins=[-100, -1, 1, 3, 100],
        labels=["Soğudu", "Değişmedi", "Hafif Isındı", "Belirgin Isındı"],
    )

    keep_cols = ["geometry", "name", "highway", "length",
                 *[f"lst_mean_{y}" for y in years], *[f"ndvi_mean_{y}" for y in years],
                 *[f"risk_score_{y}" for y in years],
                 "delta_lst", "delta_risk", "degisim_kategori"]
    roads_final = roads_valid[[c for c in keep_cols if c in roads_valid.columns]].copy()
    roads_final["degisim_kategori"] = roads_final["degisim_kategori"].astype(str)
    roads_final = roads_final.set_geometry("geometry").to_crs("EPSG:4326")
    with atomic_output_path(output_path) as temporary:
        roads_final.to_file(temporary, driver="GeoJSON")
    write_cache_meta(output_path, RISK_TIMESERIES_VERSION, fingerprint=fingerprint,
                     details={"coverage": coverage_details})

    print(f"Kaydedildi: {output_path.name} ({len(roads_final):,} yol segmenti)")
    return roads_final
