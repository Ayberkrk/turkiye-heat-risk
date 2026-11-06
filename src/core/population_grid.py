"""Yol ölçeğinde nüfus yoğunluğu: 30 m nüfus ızgarasıyla dasimetrik dağıtım.

Maruziyet grubu HVI sıralamasını en çok belirleyen grup (İzmir'de grup
skoru ile HVI arasındaki sıra korelasyonu 0,82). Ama nüfus yoğunluğu bugüne
kadar mahalle (İzmir) ya da ilçe (TÜİK şablonlu şehirler) düzeyinde sabitti:
aynı mahalledeki ana cadde ile boş sanayi sokağı aynı yoğunluğu alıyordu.

Bu modül Meta/CIESIN "High Resolution Settlement Layer" (HRSL) ızgarasını
kullanır. HRSL, sayım nüfusunu uydu görüntüsünde bina tespit edilen 30 m
hücrelere dağıtır; CC BY 4.0 lisanslıdır ve dünya geneli tek bir COG/VRT
olarak AWS Open Data'da yayımlanır. Bu yüzden şehir bbox'ının penceresi HTTP
üzerinden okunur, ülke dosyası indirilmez (İzmir için ~9 sn).

Izgara doğrudan kullanılmaz, resmi sayıma kalibre edilir (dasimetrik
yöntem). HRSL 2020 tarihlidir ve kendi sayım kaynağına dayanır; adapter'ın
verdiği güncel resmi nüfus ise yalnızca kaba birim (mahalle ya da ilçe)
düzeyindedir. Her birimin hücreleri, birim toplamı resmi nüfusa eşit
olacak şekilde ölçeklenir: birim toplamı resmi kaynaktan, birim içi
dağılım ızgaradan gelir.

Kalibrasyon birimi, resmi sayının gerçekte ait olduğu alandır. Adapter
bunları `mahalle_gdf.attrs["nufus_birimleri"]` olarak verirse (TÜİK şablonlu
şehirler: ilçe poligonunun TAMAMI ve ilçe nüfusu) onlar kullanılır: ızgara
ilçenin tamamında resmi nüfusa ölçeklenir, bbox içindeki kentsel mahalleler
ızgaradaki paylarını alır. İlçe yoğunluğu tüm ilçe alanına (kırsal hinterland
dahil) bölündüğü için, yoğunluk × bbox'taki mahalle alanı kentsel nüfusu
ilçeden ilçeye farklı oranda (Eskişehir'de 2-8 kat) eksik gösterirdi.
Verilmezse (İzmir: mahalle düzeyi nüfus) birim mahallenin kendisidir ve
resmi nüfus yoğunluk × mahalle alanıyla geri kazanılır.

HRSL'nin yaş katmanları (60+, 0-5) kullanılmaz: İzmir bbox'ında 282 bin
dolu hücrede 60+/toplam oranı yalnızca 19 farklı değer alıyor, yani yaş
payı idari birim içinde sabit dağıtılmış. Bu katman ilçe düzeyindeki
mevcut yaş verisine bilgi eklemez.
"""

from __future__ import annotations

import gc
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterstats
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds

from core.cache import atomic_output_path, is_cache_valid, write_cache_meta
from core.city_config import CityConfig
from core.paths import city_data_raw

POPULATION_GRID_ATTRIBUTION = (
    "Nüfus ızgarası: Meta & CIESIN, High Resolution Settlement Layer (CC BY 4.0)."
)

# Pencere okuma ya da kalibrasyon mantığı değişince artırılır (bkz. core/cache.py).
POPULATION_GRID_VERSION = 1

# Birim sınırındaki yolların tamponu pencerenin dışına taşmasın diye bbox'a
# eklenen pay (derece, ~2 km).
WINDOW_MARGIN_DEG = 0.02

_GDAL_HTTP_ENV = {
    # VRT 237 karoya işaret ediyor; GDAL'ın her açılışta dizin listesi
    # istemesi okuma süresini katlıyor.
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".vrt,.tif,.tiff",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


def _gdal_path(url: str) -> str:
    return f"/vsicurl/{url}" if url.startswith(("http://", "https://")) else url


def population_grid_path(config: CityConfig) -> Path:
    return city_data_raw(config.city_id) / "population_grid.tif"


def fetch_population_grid(config: CityConfig, bounds: tuple[float, float, float, float],
                          force: bool = False) -> Path:
    """Izgaranın `bounds` (EPSG:4326, [batı, güney, doğu, kuzey]) penceresini
    yerel bir GeoTIFF'e yazar ve yolunu döndürür.

    `bounds` config bbox'ı değil, nüfus birimlerinin kapsadığı alan olmalıdır:
    bbox'tan taşan bir mahallenin hücreleri pencerede olmazsa kalibrasyon o
    mahallenin resmi nüfusunu yalnızca içerideki hücrelere yığar.
    """
    url = config.population_grid_url
    if not url:
        raise ValueError(f"{config.name}: population_grid kapalı, ızgara okunamaz")
    output_path = population_grid_path(config)
    west, south, east, north = (float(v) for v in bounds)
    fingerprint = {"url": url, "bounds": [round(v, 6) for v in (west, south, east, north)],
                   "margin_deg": WINDOW_MARGIN_DEG}
    if is_cache_valid(output_path, POPULATION_GRID_VERSION, force=force, fingerprint=fingerprint):
        return output_path

    print(f"Nüfus ızgarası okunuyor: {url}")
    with rasterio.Env(**_GDAL_HTTP_ENV), rasterio.open(_gdal_path(url)) as src:
        window = from_bounds(west - WINDOW_MARGIN_DEG, south - WINDOW_MARGIN_DEG,
                             east + WINDOW_MARGIN_DEG, north + WINDOW_MARGIN_DEG, src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        data = src.read(1, window=window, masked=True).astype("float32").filled(np.nan)
        transform = src.window_transform(window)
        crs = src.crs

    profile = {
        "driver": "GTiff", "height": data.shape[0], "width": data.shape[1], "count": 1,
        "dtype": "float32", "crs": crs, "transform": transform, "nodata": np.nan,
        "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output_path(output_path) as temporary, rasterio.open(temporary, "w", **profile) as dst:
        dst.write(data, 1)
    write_cache_meta(output_path, POPULATION_GRID_VERSION, fingerprint=fingerprint)
    print(f"  {data.shape[1]}x{data.shape[0]} hücre, toplam {np.nansum(data):,.0f} kişi")
    return output_path


def calibration_units(mahalle_gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    """Nüfusun gerçekte bilindiği birimler (gerekçesi modül docstring'inde).

    Adapter `attrs["nufus_birimleri"]` verdiyse (birim, resmi_nufus, geometry)
    doğrudan onlar döner. Verilmediyse aynı ilçede aynı yoğunluğu taşıyan
    mahalleler tek birimdir ve birimin resmi nüfusu yoğunluk × alan ile geri
    kazanılır; adapter sözleşmesi nüfus sayısını değil yoğunluğu taşır.
    """
    declared = mahalle_gdf.attrs.get("nufus_birimleri")
    if declared is not None and len(declared):
        units = declared[declared["resmi_nufus"].notna()]
        return units[["birim", "resmi_nufus", "geometry"]].reset_index(drop=True)
    valid = mahalle_gdf[mahalle_gdf["nufus_yogunlugu"].notna()][["ilce_adi", "nufus_yogunlugu", "geometry"]]
    valid = valid.to_crs(crs)
    valid = valid.assign(_alan_km2=valid.geometry.area / 1e6)
    valid = valid.assign(_nufus=valid["nufus_yogunlugu"] * valid["_alan_km2"])
    # Yoğunluk float olduğu için anahtar yuvarlanır; aynı ilçe yoğunluğu
    # kopyalandığında değerler bit düzeyinde aynıdır, yuvarlama yalnızca
    # gösterim farklarına karşı bir güvence.
    key = valid["ilce_adi"].astype(str) + "|" + valid["nufus_yogunlugu"].round(6).astype(str)
    units = valid.assign(_birim=key).dissolve(by="_birim", aggfunc={"_nufus": "sum"})
    return units.reset_index()[["_birim", "_nufus", "geometry"]].rename(
        columns={"_birim": "birim", "_nufus": "resmi_nufus"}
    )


def calibrate_grid(grid: np.ndarray, transform, grid_crs, units: gpd.GeoDataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Izgara hücrelerini birim toplamları resmi nüfusa eşit olacak şekilde ölçekler.

    Bir birime düşmeyen hücreler NaN olur: oradaki yolların demografisi zaten
    yoktur ve skor almazlar (bkz. hvi.py eksiklik denetimi). İçinde hiç dolu
    hücre olmayan bir birimin nüfusu dağıtılamaz; hücreleri 0 kalır ve
    raporda `izgara_toplami == 0` olarak görünür.
    """
    units = units.to_crs(grid_crs).reset_index(drop=True)
    unit_ids = rasterize(
        ((geom, i + 1) for i, geom in enumerate(units.geometry)),
        out_shape=grid.shape, transform=transform, fill=0, dtype="int32",
    )
    filled = np.where(np.isfinite(grid), grid, 0.0)
    grid_sums = np.bincount(unit_ids.ravel(), weights=filled.ravel(), minlength=len(units) + 1)
    targets = np.concatenate([[np.nan], units["resmi_nufus"].to_numpy(dtype=float)])
    with np.errstate(invalid="ignore", divide="ignore"):
        factors = np.where(grid_sums > 0, targets / grid_sums, 0.0)
    factors[0] = np.nan
    calibrated = (filled * factors[unit_ids]).astype("float32")

    report = units.drop(columns="geometry").assign(
        izgara_toplami=grid_sums[1:], kalibrasyon_carpani=factors[1:],
    )
    return calibrated, report


def road_population_density(roads_utm: gpd.GeoDataFrame, calibrated: np.ndarray, transform, grid_crs,
                            buffer_m: float, chunk_size: int = 4000) -> pd.Series:
    """Her yolun `buffer_m` tamponundaki kalibre nüfusu, kişi/km² olarak.

    Tampon UTM'de çizilir, alanı da orada ölçülür; toplama için ızgaranın
    CRS'ine (EPSG:4326) çevrilir. Hücreler kişi SAYISI taşıdığı için
    derece ızgarasındaki hücre alanı farkı toplamı bozmaz. Yollar parça
    parça işlenir (8 GB RAM, bkz. hvi._building_density_per_km2).
    """
    parts = []
    for start in range(0, len(roads_utm), chunk_size):
        chunk = roads_utm.iloc[start:start + chunk_size]
        buffers = chunk.geometry.buffer(buffer_m)
        stats = rasterstats.zonal_stats(
            gpd.GeoSeries(buffers, crs=roads_utm.crs).to_crs(grid_crs), calibrated,
            affine=transform, stats=["sum", "count"], nodata=np.nan, all_touched=False,
        )
        sums = np.array([s["sum"] if s["count"] else np.nan for s in stats], dtype=float)
        area_km2 = buffers.area.to_numpy() / 1e6
        with np.errstate(invalid="ignore", divide="ignore"):
            parts.append(pd.Series(np.where(area_km2 > 0, sums / area_km2, np.nan), index=chunk.index))
        del buffers, stats
        gc.collect()
    return pd.concat(parts) if parts else pd.Series(dtype=float)


def compute_road_population_density(config: CityConfig, roads_utm: gpd.GeoDataFrame,
                                    mahalle_gdf: gpd.GeoDataFrame, buffer_m: float,
                                    force: bool = False) -> tuple[pd.Series, pd.DataFrame]:
    """Uçtan uca: pencereyi oku, resmi nüfusa kalibre et, yollara örnekle."""
    units = calibration_units(mahalle_gdf, config.crs)
    bounds = units.to_crs("EPSG:4326").total_bounds
    grid_path = fetch_population_grid(config, tuple(bounds), force=force)
    with rasterio.open(grid_path) as src:
        grid = src.read(1)
        transform, grid_crs = src.transform, src.crs
    calibrated, report = calibrate_grid(grid, transform, grid_crs, units)
    del grid

    empty_units = int((report["izgara_toplami"] <= 0).sum())
    factors = report.loc[report["izgara_toplami"] > 0, "kalibrasyon_carpani"]
    print(f"  {len(report)} kalibrasyon birimi, çarpan medyanı {factors.median():.2f} "
          f"(%5-%95: {factors.quantile(0.05):.2f}-{factors.quantile(0.95):.2f})")
    if empty_units:
        print(f"  UYARI: {empty_units} birimde ızgara boş, resmi nüfusu dağıtılamadı")

    density = road_population_density(roads_utm, calibrated, transform, grid_crs, buffer_m)
    return density, report
