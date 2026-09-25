"""İlçe düzeyinde statik referans tablolarından mahalle katmanı üreten ortak mantık.

Belediyenin kendi CKAN açık veri portalı olmayan şehirler için (bkz.
`cities/eskisehir`, `cities/sanliurfa`, `cities/antalya`, ...) demografi,
TÜİK'in herkese açık ADNKS yayınlarından ve resmi SEGE-2022 raporundan
alınmış iki küçük CSV'den gelir:

  - `ilce_nufus.csv` (`;` ayraçlı): `ILCE;NUFUS;YASLI_ORAN;COCUK_ORAN`
  - `sege_2022_ilce.csv` (`;` ayraçlı): en az `ILCE;SKOR`

Bu modül, şehre özel hiçbir şey bilmez - o şehrin adapter'ı sadece kendi
CSV yollarını verir (bkz. CONTRIBUTING.md'deki adapter sözleşmesi). Böylece
yeni bir TÜİK-şablonlu şehir eklemek, ~100 satırlık bu mantığı kopyalamak
yerine iki CSV ve ince bir `adapter.py` yazmaktan ibarettir.

Sınırlama (tüm bu şehirler için ortak): yaşlı/çocuk oranı da nüfus
yoğunluğu da ilçe düzeyinde sabittir, mahalle içi farkı yakalamaz.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from core.city_config import CityConfig
from core.text_utils import normalize_name


def build_neighborhood_layer_from_ilce_tables(
    pbf_path: Path, config: CityConfig, ilce_nufus_csv: Path, sege_csv: Path,
) -> gpd.GeoDataFrame:
    """Mahalle sınırlarını ilçe bazlı nüfus yoğunluğu, yaşlı/çocuk oranı ve
    sosyoekonomik skorla zenginleştirir.
    """
    west, south, east, north = config.bbox
    osm_gdf = gpd.read_file(pbf_path, layer="multipolygons", bbox=(west, south, east, north))

    ilce_gdf = osm_gdf[
        (osm_gdf["admin_level"] == config.admin_level_ilce) & (osm_gdf["boundary"] == "administrative")
    ][["name", "geometry"]].rename(columns={"name": "ilce_adi"}).reset_index(drop=True)

    mahalle_gdf = osm_gdf[
        (osm_gdf["admin_level"] == config.admin_level_mahalle) & (osm_gdf["boundary"] == "administrative")
    ][["name", "geometry"]].rename(columns={"name": "mahalle_adi"}).reset_index(drop=True)

    # Mahalle-ilçe eşlemesi isim yerine konumsal sorguyla (centroid içinde mi)
    # yapılır - aynı isimli mahalleler çok yaygın (bkz. cities/izmir/adapter.py).
    mahalle_utm = mahalle_gdf.to_crs(config.crs)
    mahalle_gdf["centroid"] = mahalle_utm.geometry.centroid.to_crs("EPSG:4326")
    mahalle_pts = mahalle_gdf.set_geometry("centroid")[["mahalle_adi", "centroid"]]
    mahalle_pts = mahalle_pts.rename(columns={"centroid": "geometry"}).set_geometry("geometry")
    mahalle_pts.crs = mahalle_gdf.crs

    joined = gpd.sjoin(mahalle_pts, ilce_gdf, how="left", predicate="within")
    mahalle_gdf["ilce_adi"] = joined["ilce_adi"].values
    mahalle_gdf = mahalle_gdf.drop(columns=["centroid"]).dropna(subset=["ilce_adi"])
    mahalle_gdf["ilce_norm"] = mahalle_gdf["ilce_adi"].apply(normalize_name)

    # İlçe alanı buradan (OSM sınırından) hesaplanır - TÜİK'in kendi alan
    # rakamı yerine, mahalle-ilçe eşlemesiyle aynı geometriden türetilerek
    # tutarlılık sağlanır.
    ilce_gdf["ilce_norm"] = ilce_gdf["ilce_adi"].apply(normalize_name)
    ilce_utm = ilce_gdf.to_crs(config.crs)
    ilce_alan_km2 = (ilce_utm.geometry.area / 1e6).rename("ilce_alan_km2")
    ilce_alan_km2.index = ilce_gdf["ilce_norm"]

    nufus = pd.read_csv(ilce_nufus_csv, sep=";", encoding="utf-8")
    nufus["ilce_norm"] = nufus["ILCE"].apply(normalize_name)
    nufus = nufus.set_index("ilce_norm").join(ilce_alan_km2, how="left")
    nufus["nufus_yogunlugu"] = nufus["NUFUS"] / nufus["ilce_alan_km2"]

    mahalle_gdf = mahalle_gdf.merge(
        nufus[["nufus_yogunlugu", "YASLI_ORAN", "COCUK_ORAN"]].rename(
            columns={"YASLI_ORAN": "yasli_oran", "COCUK_ORAN": "cocuk_oran"}
        ),
        left_on="ilce_norm", right_index=True, how="left",
    )

    sege = pd.read_csv(sege_csv, sep=";", encoding="utf-8")
    sege["ilce_norm"] = sege["ILCE"].apply(normalize_name)
    sege_skor = sege.set_index("ilce_norm")["SKOR"].rename("sosyoekonomik_skor")
    mahalle_gdf = mahalle_gdf.merge(sege_skor, left_on="ilce_norm", right_index=True, how="left")

    # bbox, CSV'de olmayan bir ilçenin mahallelerini de içine alırsa o
    # mahallelerin tüm demografi sütunları sessizce NaN kalır ve oradaki
    # yollar HVI'dan dışlanır - config'teki bbox'ı daraltma ya da CSV'ye
    # ilçeyi ekleme ihtiyacını erken göstermek için burada görünür kılınır.
    eksik = sorted(set(mahalle_gdf.loc[mahalle_gdf["nufus_yogunlugu"].isna(), "ilce_adi"]))
    if eksik:
        print(f"UYARI: {config.name} - ilce_nufus.csv'de olmayan ilçeler (verileri NaN kalır): {eksik}")

    return mahalle_gdf
