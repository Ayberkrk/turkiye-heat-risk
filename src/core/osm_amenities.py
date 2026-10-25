"""OSM pbf'inden sağlık hizmeti, yeşil alan ve bina yoğunluğu katmanlarını çıkarır.

Bu üç katman da zaten indirilmiş olan `.osm.pbf` özütünden türetilir - ek
bir dış veri kaynağına ihtiyaç yoktur. Varsayılan OGR "osm" şeması, nokta
katmanında (`points`) `amenity` gibi etiketleri ayrı sütun olarak değil,
`other_tags` içinde HSTORE benzeri bir dizgede tutar; bu yüzden nokta
katmanı için basit bir regex ayrıştırması gerekir. `multipolygons`
katmanında ise `amenity`, `landuse`, `leisure`, `building` zaten birinci
sınıf sütunlardır.
"""

from __future__ import annotations

import re

import geopandas as gpd
import pandas as pd

from core.city_config import CityConfig

HEALTH_AMENITIES = {"hospital", "clinic", "pharmacy", "doctors"}
# Keep the OSM facility classes distinct in output diagnostics. `doctors` is
# not silently treated as a clinic, even though both are outpatient services.
HEALTH_AMENITY_GROUPS = {
    "hastane": {"hospital"},
    "klinik": {"clinic"},
    "doktor": {"doctors"},
    "eczane": {"pharmacy"},
}
_HEALTHCARE_TO_AMENITY = {
    "hospital": "hospital",
    "clinic": "clinic",
    "doctor": "doctors",
    "doctors": "doctors",
    "pharmacy": "pharmacy",
}
GREEN_LEISURE = {"park", "garden", "nature_reserve"}
GREEN_LANDUSE = {"forest", "grass", "meadow", "recreation_ground"}

_OTHER_TAG_RE = re.compile(r'"([^"]+)"=>"([^"]*)"')


def _other_tags_get(other_tags: object, key: str) -> str | None:
    if not isinstance(other_tags, str):
        return None
    for tag_key, tag_val in _OTHER_TAG_RE.findall(other_tags):
        if tag_key == key:
            return tag_val
    return None


def _health_amenity(amenity: object, healthcare: object) -> str | None:
    """Normalize supported amenity=* and healthcare=* tags to one class."""
    if isinstance(amenity, str) and amenity in HEALTH_AMENITIES:
        return amenity
    if isinstance(healthcare, str):
        return _HEALTHCARE_TO_AMENITY.get(healthcare)
    return None


def load_health_points(config: CityConfig, pbf_path) -> gpd.GeoDataFrame:
    """Hastane/klinik/eczane/doktor noktalarını ve ayak izlerini birleştirir.

    Point facilities stay points and mapped facility polygons stay polygons.
    Nearest-distance queries can measure to either geometry; replacing a
    polygon by its centroid overstates access distance for large facilities.
    """
    west, south, east, north = config.bbox
    bbox = (west, south, east, north)

    points = gpd.read_file(pbf_path, layer="points", bbox=bbox)
    points = points.copy()
    amenity_tags = points["amenity"] if "amenity" in points.columns else pd.Series(None, index=points.index)
    healthcare_tags = (
        points["healthcare"] if "healthcare" in points.columns
        else points.get("other_tags", pd.Series(None, index=points.index)).apply(
            lambda tags: _other_tags_get(tags, "healthcare")
        )
    )
    if "other_tags" in points.columns and "amenity" not in points.columns:
        amenity_tags = points["other_tags"].apply(lambda tags: _other_tags_get(tags, "amenity"))
    points["amenity"] = [
        _health_amenity(amenity, healthcare)
        for amenity, healthcare in zip(amenity_tags, healthcare_tags)
    ]
    health_points = points[points["amenity"].isin(HEALTH_AMENITIES)][["geometry", "amenity"]]

    polys = gpd.read_file(
        pbf_path, layer="multipolygons", bbox=bbox, columns=["amenity", "other_tags", "geometry"]
    ).copy()
    amenity_tags = polys["amenity"] if "amenity" in polys.columns else pd.Series(None, index=polys.index)
    healthcare_tags = (
        polys["healthcare"] if "healthcare" in polys.columns
        else polys.get("other_tags", pd.Series(None, index=polys.index)).apply(
            lambda tags: _other_tags_get(tags, "healthcare")
        )
    )
    polys["amenity"] = [
        _health_amenity(amenity, healthcare)
        for amenity, healthcare in zip(amenity_tags, healthcare_tags)
    ]
    health_polys = polys[polys["amenity"].isin(HEALTH_AMENITIES)][["geometry", "amenity"]]
    combined = pd.concat([health_points, health_polys], ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=points.crs)


def load_green_space_polygons(config: CityConfig, pbf_path) -> gpd.GeoDataFrame:
    """Park/bahçe/orman/çayır gibi yeşil alan poligonlarını döndürür."""
    west, south, east, north = config.bbox
    # Bina katmanındaki gibi sütun filtresi kullanılıyor: `multipolygons`
    # katmanının tamamını okumak 8 GB RAM'lik bir makinede gereksiz yük.
    polys = gpd.read_file(
        pbf_path, layer="multipolygons", bbox=(west, south, east, north),
        columns=["leisure", "landuse", "geometry"],
    )
    is_green = polys["leisure"].isin(GREEN_LEISURE) | polys["landuse"].isin(GREEN_LANDUSE)
    green = polys[is_green][["geometry", "leisure", "landuse"]].copy()
    return green[green.geometry.notna() & ~green.geometry.is_empty]


def load_building_centroids(config: CityConfig, pbf_path) -> gpd.GeoDataFrame:
    """Bina ayak izlerinin merkez noktalarını döndürür (yoğunluk hesaplamak için).

    Yapılaşma yoğunluğu için tam bina poligonlarıyla (İzmir'de ~380 bin
    kayıt) çalışmak yerine sadece merkez noktaları kullanılır - 8 GB RAM'lik
    bir makinede 44 bin yol tampon poligonuna karşı 380 bin tam poligon
    join'i yerine, çok daha hafif nokta-içinde-mi sorgusu koşulur.
    """
    west, south, east, north = config.bbox
    polys = gpd.read_file(
        pbf_path, layer="multipolygons", bbox=(west, south, east, north), columns=["building", "geometry"]
    )
    buildings = polys[polys["building"].notna()][["geometry"]].copy()
    # bkz. load_health_points'teki aynı düzeltme - centroid coğrafi CRS'te
    # değil, önce config.crs'e geçilip orada hesaplanmalı.
    original_crs = buildings.crs
    buildings["geometry"] = buildings.to_crs(config.crs).geometry.centroid.to_crs(original_crs)
    return buildings
