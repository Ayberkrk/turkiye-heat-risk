"""Bir şehrin bbox'ının, demografisi eşlenmiş mahallelerle ne kadar örtüştüğünü ölçer.

`hvi.py` her yolu merkez noktasının düştüğü mahalleden demografi alır;
demografisi (yoğunluk, yaşlı/çocuk oranı, varsa SEGE skoru) NaN olan bir
mahalleye düşen yol HVI'dan dışlanır. bbox yanlış yere çizildiyse ya da
adapter'ın ilçe adı OSM'dekiyle eşleşmiyorsa bu oran sıfıra iner ve
pipeline ancak çok sonra, HVI hesabında anlaşılmaz bir hatayla (boş dizide
Jenks) patlar. Burada aynı eşlemeyi HVI'dan önce, ucuza ölçüyoruz.

CSV bütünlük testleri bunu yakalayamaz: yalnızca gerçek OSM sınırlarıyla
karşılaştırınca ortaya çıkar (bkz. `validate_city.py --osm-coverage`).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from core.city_config import CityConfig, load_population_adapter

# Bir mahallenin "demografisi eşlenmiş" sayılması için dolu olması gereken
# sütunlar; sosyoekonomik_skor adapter'a bağlı isteğe bağlı bir sütundur.
_REQUIRED_DEMOGRAPHY = ("nufus_yogunlugu", "yasli_oran", "cocuk_oran")


def road_coverage(mahalle_gdf: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, crs: str) -> float:
    """Yolların, demografisi tam olan bir mahalleye düşen payını (0-1) döner.

    Yol merkez noktası (projeksiyonlu CRS'te hesaplanır, bkz. `hvi.py`)
    mahalle poligonunun içindeyse eşleşmiş sayılır. Yol ya da mahalle yoksa 0.
    """
    if len(roads) == 0 or len(mahalle_gdf) == 0:
        return 0.0

    columns: list[str] = list(_REQUIRED_DEMOGRAPHY)
    if "sosyoekonomik_skor" in mahalle_gdf.columns:
        columns.append("sosyoekonomik_skor")
    complete = mahalle_gdf[mahalle_gdf[columns].notna().all(axis=1)][["geometry"]]
    if len(complete) == 0:
        return 0.0

    points = gpd.GeoDataFrame(geometry=roads.to_crs(crs).geometry.centroid, crs=crs).to_crs(complete.crs)
    joined = gpd.sjoin(points, complete, predicate="within", how="left")
    # Üst üste binen mahalle poligonları bir yolu birden fazla satıra çoğaltabilir.
    return float(joined["index_right"].notna().groupby(level=0).any().mean())


def measure_city_coverage(config: CityConfig, pbf_path: Path) -> dict:
    """Şehrin adapter'ını gerçek OSM özütüne karşı çalıştırıp kapsamı ölçer.

    Döner: mahalle/yol sayıları, ilçe adları ve `coverage` (0-1).
    """
    adapter = load_population_adapter(config)
    mahalle = adapter.build_neighborhood_layer(pbf_path, adapter.fetch_population_data(config), config)

    roads = gpd.read_file(pbf_path, layer="lines", bbox=tuple(config.bbox), columns=["highway", "geometry"])
    roads = roads[roads["highway"].isin(config.drive_highway_types)]

    return {
        "mahalle": len(mahalle),
        "yol": len(roads),
        "ilce": sorted(mahalle["ilce_adi"].unique()) if len(mahalle) else [],
        "coverage": road_coverage(mahalle, roads, config.crs),
    }
