"""Çok bileşenli, açıklanabilir Isı Hassasiyet Endeksi (HVI).

Eski sürüm HVI'yi sadece üç bileşenin (Tehlike × Maruziyet × Hassasiyet)
çarpımı olarak hesaplıyordu. Bu modül, değişken sayıda 0-1 normalize
bileşeni birleştirebilecek genel bir yapı sunar; her bileşenin kendi
normalize değeri de nihai skorla birlikte GeoJSON'a yazılır - böylece bir
kullanıcı "bu yolun HVI'si neden yüksek?" sorusuna haritadan doğrudan
cevap bulabilir.

Bileşenler:
  - hazard              : LST risk skoru (yıl bazlı, zaten vardı)
  - exposure             : nüfus yoğunluğu (zaten vardı)
  - sensitivity_yasli     : 65+ nüfus oranı (zaten vardı)
  - sensitivity_cocuk     : 0-14 nüfus oranı (yeni - aynı CSV'den, ek maliyetsiz)
  - sensitivity_agac      : yol tamponundaki ortalama NDVI'nin tersi (yeni -
                             zaten hesaplanan NDVI mozaiğinden, ağaç örtüsü/gölge proxysi)
  - sensitivity_saglik    : en yakın hastane/klinik/eczaneye uzaklık (yeni - OSM'den)
  - sensitivity_yesil     : en yakın park/orman/çayır poligonuna uzaklık (yeni - OSM'den)
  - sensitivity_yapilasma : yol tamponu çevresindeki bina yoğunluğu (yeni - OSM'den)
  - sensitivity_sosyoekonomik : ilçe bazlı sosyoekonomik gelişmişlik skorunun
                             tersi (yeni - resmi SEGE-2022 raporundan, bkz.
                             cities/izmir/adapter.py)

Birleştirme iki aşamalıdır (bkz. `COMPONENT_GROUPS`):
  1. Bileşenler üç grupta toplanır: Tehlike (LST), Maruziyet (nüfus ve
     yapılaşma yoğunluğu), Kırılganlık (yaşlı, çocuk, sosyoekonomik, sağlık
     ve yeşil alan erişimi, ağaç örtüsü). Grup içi skor üyelerin aritmetik
     ortalamasıdır - aynı grubun üyeleri birbirini telafi edebilir.
  2. Grup skorları, tüm yılların ortak dağılımına göre yeniden 0-1'e
     ölçeklenir. Ortalama almak yayılımı daraltır (altı bileşenli grupta
     bileşenler birbirini götürür: yaşlı ve çocuk oranı ters ilişkilidir);
     bu adım olmadan dar bantta kalan grup, geometrik ortalamada sıralamayı
     hiç etkilemiyordu (İzmir'de kırılganlık grubunun skorla sıra
     korelasyonu 0,00 idi).
  3. Üç grup skorunun **geometrik ortalaması** × 100 nihai skordur - gruplar
     birbirini telafi edemez: sıcak olmayan ya da kimsenin yaşamadığı bir
     yolda risk düşük kalır.

Önceki sürüm dokuz bileşenin düz geometrik ortalamasıydı. Orada bileşen
sayısı gizli bir ağırlıktı: yedi kırılganlık bileşenine karşı tek bir
sıcaklık bileşeni, "ısı" endeksinde sıcaklığın payını 1/9'a indiriyordu ve
birbiriyle ilişkili bileşenler (NDVI ile LST, bina ile nüfus yoğunluğu) aynı
sinyali iki kez sayıyordu. Gruplu yapıda her grubun payı, kaç bileşen
içerdiğinden bağımsız olarak 1/3'tür.

Ölçekleme: bileşenler min-max yerine %2-%98 yüzdelik aralığına göre 0-1'e
çekilir (`robust_normalize_0_1`). Min-max'ta tek bir uç yol (ör. hastaneye
40 km uzaktaki bir kırsal segment) geri kalan tüm yolları ölçeğin dar bir
bandına sıkıştırıyordu.

Ayırt etmeyen bileşenler: bir bileşen şehrin tüm yollarında aynı değeri
alıyorsa (tek ilçeli şehirlerde ilçe düzeyindeki dört demografik bileşen)
grup ortalamasına alınmaz; aksi halde sabit bir 0, grubun geri kalan
üyelerinin etkisini seyreltirdi.

Yıllar arası karşılaştırılabilirlik: `hvi_percentage` ve Jenks kategori
sınırları TÜM yılların ortak dağılımından hesaplanır. Her yıl kendi içinde
0-100'e ölçeklenseydi, tanım gereği her yılın en kötü yolu %100 çıkar ve
"2026'da risk arttı" demek imkansız olurdu. LST risk skorunda (`core/roads.py`)
uygulanan ortak ölçek mantığının aynısı burada da geçerlidir.
"""

from __future__ import annotations

import gc

import geopandas as gpd
import jenkspy
import numpy as np
import pandas as pd

from core.cache import is_cache_valid, write_cache_meta
from core.city_config import CityConfig, load_population_adapter
from core.osm_amenities import load_building_centroids, load_green_space_polygons, load_health_points
from core.paths import city_data_proc, resolve_pbf_path

CATEGORY_COLORS_5 = {
    "Düşük": "#3182bd",
    "Orta": "#fdae6b",
    "Yüksek": "#fd8d3c",
    "Kritik": "#de2d26",
    "Aşırı Kritik": "#800026",
}
CATEGORY_ORDER_5 = list(CATEGORY_COLORS_5)

BUCKET_LABELS_5 = ["çok düşük", "düşük", "orta", "yüksek", "çok yüksek"]
BUCKET_LABELS_5_DISTANCE = ["çok yakın", "yakın", "orta", "uzak", "çok uzak"]
BUCKET_LABELS_5_DENSITY = ["çok seyrek", "seyrek", "orta", "yoğun", "çok yoğun"]

# Bina yoğunluğu için yol tamponu, LST örneklemesinde kullanılan dar
# tampondan (varsayılan 10 m) ayrıdır: bina merkez noktaları yol eksenine
# tipik olarak 10 m'den uzakta kaldığı için dar tamponla ölçüm yolların
# yarısından fazlasında 0 çıkıyordu. 150 m, bir yolun çevresindeki kentsel
# doku için makul bir yürüme mesafesi ölçeğidir.
BUILDING_DENSITY_BUFFER_M = 150

# Geometrik ortalama alınmadan önce her grup skorunun ölçekleneceği alt sınır
# (gerekçesi `combine_groups` içinde).
COMPONENT_FLOOR = 0.05

# Çıktı sürümü - bileşen sayısı/formülü, yapılaşma tamponu veya
# `roads_with_hvi.geojson` sütun şeması değiştiğinde artırılır; eski önbellek
# güncel çıktı gibi kullanılmamalıdır (bkz. core/cache.py).
HVI_FORMULA_VERSION = 4


# Sağlam (aykırı değere dayanıklı) ölçeklemede kullanılan alt/üst yüzdelikler.
# Bu aralığın dışındaki değerler 0 ya da 1'e kırpılır.
ROBUST_QUANTILES = (0.02, 0.98)

# Bileşenlerin ait olduğu gruplar. Grup içi aritmetik, gruplar arası
# geometrik ortalama alınır (gerekçesi modül docstring'inde). Yıl bazlı
# bileşenler burada yıl eki olmadan anılır.
COMPONENT_GROUPS = {
    "hazard": ["hazard_norm"],
    "exposure": ["exposure_norm", "sensitivity_yapilasma_norm"],
    "vulnerability": [
        "sensitivity_yasli_norm", "sensitivity_cocuk_norm", "sensitivity_sosyoekonomik_norm",
        "sensitivity_saglik_norm", "sensitivity_yesil_norm", "sensitivity_agac_norm",
    ],
}


def normalize_0_1(series: pd.Series) -> pd.Series:
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return series * 0
    return (series - min_v) / (max_v - min_v)


def robust_bounds(series: pd.Series, quantiles: tuple[float, float] = ROBUST_QUANTILES) -> tuple[float, float]:
    """Ölçeklemede kullanılacak (alt, üst) sınırı yüzdeliklerden döndürür.

    İki yüzdelik çakışırsa (ör. yolların %97'si aynı ilçede olduğu için ilçe
    düzeyindeki bir oran neredeyse sabitse) min-max'a geri düşülür; aksi
    halde gerçekte değişen bir bileşen tümüyle 0'a çökerdi.
    """
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return float("nan"), float("nan")
    low, high = float(clean.quantile(quantiles[0])), float(clean.quantile(quantiles[1]))
    if low == high:
        low, high = float(clean.min()), float(clean.max())
    return low, high


def scale_between(series: pd.Series, low: float, high: float) -> pd.Series:
    """Seriyi [low, high] aralığına göre 0-1'e çeker, dışarıda kalanı kırpar."""
    if not (np.isfinite(low) and np.isfinite(high)) or high == low:
        return series * 0
    return ((series - low) / (high - low)).clip(0, 1)


def robust_normalize_0_1(series: pd.Series) -> pd.Series:
    return scale_between(series, *robust_bounds(series))


def informative_components(values: pd.DataFrame, columns: list[str]) -> list[str]:
    """`columns` içinden en az iki farklı değer alan (ayırt eden) sütunları döndürür."""
    return [column for column in columns if values[column].nunique(dropna=True) > 1]


def group_scores(values: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Bileşenleri `COMPONENT_GROUPS`'a göre grup skorlarına indirger.

    `values` sütunları yıl eki taşımayan bileşen adlarıdır; yalnızca mevcut
    sütunlar kullanılır, hiç üyesi olmayan grup çıktıda yer almaz. Bir
    satırda herhangi bir üye NaN ise o grubun skoru da NaN olur.
    """
    weights = weights or {}
    result = {}
    for group, members in COMPONENT_GROUPS.items():
        present = [column for column in members if column in values.columns]
        if not present:
            continue
        member_weights = np.asarray([weights.get(column, 1.0) for column in present], dtype=float)
        result[group] = values[present].to_numpy(dtype=float) @ (member_weights / member_weights.sum())
    return pd.DataFrame(result, index=values.index)


def combine_groups(groups: pd.DataFrame, group_weights: dict[str, float] | None = None) -> pd.Series:
    """Grup skorlarının (0-1) ağırlıklı geometrik ortalaması × 100.

    Skorlar önce [COMPONENT_FLOOR, 1] aralığına ölçeklenir: 0, "hiç risk yok"
    değil "veri kümesindeki en düşük değer" demektir ve tek başına tüm skoru
    sıfırlamamalıdır. Taban, "bir grup düşükse toplam risk de düşer"
    davranışını korur ama etkisini sürekli ve sınırlı tutar.
    """
    group_weights = group_weights or {}
    w = np.asarray([group_weights.get(group, 1.0) for group in groups.columns], dtype=float)
    floored = COMPONENT_FLOOR + (1 - COMPONENT_FLOOR) * groups.to_numpy(dtype=float)
    return pd.Series(np.exp(np.log(floored) @ (w / w.sum())) * 100, index=groups.index)


def pooled_group_bounds(tables: list[pd.DataFrame],
                        weights: dict[str, float] | None = None) -> dict[str, tuple[float, float]]:
    """Grup skorlarının yeniden ölçekleneceği sınırları, verilen tüm tablolardan
    (tipik olarak her yıl için bir tablo) ORTAK olarak hesaplar.

    Sınırlar yıl başına ayrı hesaplansaydı aynı grup skoru iki yılda farklı
    değere ölçeklenir ve yıllar karşılaştırılamazdı.
    """
    groups = pd.concat([group_scores(table, weights) for table in tables], ignore_index=True)
    return {group: robust_bounds(groups[group]) for group in groups.columns}


def rescale_groups(groups: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Grup skorlarını `bounds`'a göre 0-1'e çeker (gerekçesi modül docstring'inde)."""
    return pd.DataFrame(
        {group: scale_between(groups[group], *bounds[group]) for group in groups.columns}, index=groups.index,
    )


def hvi_from_components(values: pd.DataFrame, weights: dict[str, float] | None = None,
                        bounds: dict[str, tuple[float, float]] | None = None) -> pd.Series:
    """Bileşen tablosundan nihai skoru üretir (grup içi aritmetik, gruplar arası geometrik).

    `weights` verilmezse her bileşen grubunda, her grup da endekste eşit
    paya sahiptir. Verilirse (duyarlılık analizi, bkz. core/impact_analysis.py)
    bileşen ağırlıkları grup içinde uygulanır, grubun ağırlığı da üyelerinin
    ağırlık ortalamasıdır.

    `bounds` grup skorlarının yeniden ölçekleme sınırlarıdır (bkz.
    pooled_group_bounds); birden fazla tablo (yıl, senaryo) karşılaştırılacaksa
    hepsine AYNI sınırlar verilmelidir. Verilmezse yalnızca bu tablodan hesaplanır.
    """
    weights = weights or {}
    groups = group_scores(values, weights)
    groups = rescale_groups(groups, bounds or pooled_group_bounds([values], weights))
    group_weights = {
        group: float(np.mean([weights.get(column, 1.0) for column in COMPONENT_GROUPS[group]
                              if column in values.columns]))
        for group in groups.columns
    }
    return combine_groups(groups, group_weights)


def bucket_5(series: pd.Series, labels: list[str]) -> pd.Series:
    """Bir seriyi yüzdelik dilimlerine göre 5 etikete ayırır.

    Eşit genişlikte aralıklar (0-0.2, 0.2-0.4, ...) kullanılmıyor: gerçek
    veriler çok çarpık dağıldığı için birkaç uç değer tüm aralığı ele
    geçiriyor ve etiketler bilgi taşımaz hale geliyordu (ör. yolların
    %91'i "hastaneye çok yakın" çıkıyordu). Sıralamaya (rank) göre
    bölmek, her etiketin yolların yaklaşık beşte birine denk gelmesini
    garanti eder. Eşit değerler ortalama sıra alır, böylece çok sayıda
    tekrar eden değer olsa bile fonksiyon her zaman 5 etiket üretir.
    """
    pct = series.rank(pct=True, method="average")
    return pd.cut(pct, bins=[-0.001, 0.2, 0.4, 0.6, 0.8, 1.001], labels=labels)


def _nearest_distance_m(points_utm: gpd.GeoSeries, targets_wgs84: gpd.GeoDataFrame, crs: str) -> pd.Series:
    """Her nokta için en yakın hedefe olan mesafeyi (metre) döndürür.

    `points_utm`'in orijinal (muhtemelen boşluklu) indeksi korunur; iç
    hesap için 0..n-1 pozisyonel bir indekse geçilip sonda geri eşlenir -
    bu, sjoin_nearest'in eşit mesafede satır çoğaltma davranışına karşı
    orijinal indeks değerlerinin çakışma/boşluk durumundan bağımsız çalışır.
    """
    if len(targets_wgs84) == 0:
        return pd.Series(np.nan, index=points_utm.index)

    targets_utm = targets_wgs84.to_crs(crs)
    left = gpd.GeoDataFrame(geometry=points_utm.reset_index(drop=True), crs=crs)
    joined = gpd.sjoin_nearest(left, targets_utm[["geometry"]], how="left", distance_col="dist_m")
    # sjoin_nearest eşit mesafede birden fazla eşleşme varsa satırı çoğaltabilir;
    # left'in pozisyonel indeksine göre gruplayıp en küçük mesafeyi al.
    nearest = joined.groupby(joined.index)["dist_m"].min()
    values = nearest.reindex(range(len(points_utm))).to_numpy()
    return pd.Series(values, index=points_utm.index)


def _building_density_per_km2(building_centroids_utm: gpd.GeoDataFrame, roads_utm: gpd.GeoDataFrame,
                               buffer_m: int = BUILDING_DENSITY_BUFFER_M, chunk_size: int = 4000) -> pd.Series:
    """Her yolun çevresindeki bina yoğunluğunu (bina/km²) döndürür.

    Yolun etrafına `buffer_m` yarıçapında bir tampon çizilir ve içine merkezi
    düşen bina sayısı tamponun alanına bölünür. Tampon, LST örneklemesinde
    kullanılan dar tampondan (`config.buffer_meters`) kasıtlı olarak ayrıdır -
    gerekçesi `BUILDING_DENSITY_BUFFER_M` yanındaki notta.

    Bellek: sonuç 8 GB RAM'lik bir makinede de üretilebilmeli. Bu yüzden
    geopandas `sjoin` (eşleşen her bina-yol çifti için tam bir satır üretir)
    yerine doğrudan konumsal indeks sorgusu kullanılıyor; bu sorgu sadece iki
    tamsayı dizisi döndürür, geometri kopyalamaz. Yollar ayrıca parça parça
    işlenir, böylece aynı anda yalnızca `chunk_size` kadar tampon poligonu
    bellekte tutulur.
    """
    tree = building_centroids_utm.sindex
    all_index = roads_utm.index
    parts = []

    for start in range(0, len(all_index), chunk_size):
        chunk_index = all_index[start:start + chunk_size]
        buffers = roads_utm.loc[chunk_index].geometry.buffer(buffer_m)
        # query() (tampon, bina) pozisyon çiftlerini verir; satır 0 tampon
        # sırası, satır 1 bina sırasıdır. Sadece saymak yeterli.
        hits = tree.query(buffers, predicate="contains")
        counts = np.bincount(hits[0], minlength=len(buffers))
        area_km2 = buffers.area.to_numpy() / 1e6
        with np.errstate(invalid="ignore", divide="ignore"):
            density = np.where(area_km2 > 0, counts / area_km2, np.nan)
        parts.append(pd.Series(density, index=chunk_index))
        del buffers, hits, counts, area_km2, density
        gc.collect()

    return pd.concat(parts)


def compute_heat_vulnerability_index(config: CityConfig, years: list[str],
                                      roads: gpd.GeoDataFrame, force: bool = False) -> gpd.GeoDataFrame:
    """Çok bileşenli HVI'yi hesaplar; her bileşenin normalize değerini ve nihai
    skoru/kategoriyi GeoJSON'a yazacak sütunlar olarak ekler.
    """
    output_path = city_data_proc(config.city_id) / "roads_with_hvi.geojson"
    if is_cache_valid(output_path, HVI_FORMULA_VERSION, force=force):
        print("roads_with_hvi.geojson güncel, atlanıyor")
        return gpd.read_file(output_path)

    adapter = load_population_adapter(config)
    population_paths = adapter.fetch_population_data(config)
    pbf_path = resolve_pbf_path(config.city_id)
    mahalle_gdf = adapter.build_neighborhood_layer(pbf_path, population_paths, config)

    roads = roads.copy()
    roads_utm = roads.to_crs(config.crs)
    roads["centroid"] = roads_utm.geometry.centroid.to_crs("EPSG:4326")
    road_pts = roads.set_geometry("centroid")[["centroid"]].set_geometry("centroid")
    road_pts.crs = roads.crs

    # "sosyoekonomik_skor" isteğe bağlıdır - her şehir adapter'ı güvenilir bir
    # sosyoekonomik gösterge bulamayabilir; bu durumda bileşen sessizce
    # dışarıda bırakılır, core kodu değişmez.
    has_sosyoekonomik = "sosyoekonomik_skor" in mahalle_gdf.columns
    optional_cols = ["sosyoekonomik_skor"] if has_sosyoekonomik else []
    mahalle_cols = mahalle_gdf[["mahalle_adi", "ilce_adi", "nufus_yogunlugu", "yasli_oran", "cocuk_oran",
                                 *optional_cols, "geometry"]]
    joined = gpd.sjoin(road_pts, mahalle_cols, how="left", predicate="within")
    roads["mahalle_adi"] = joined["mahalle_adi"].values
    # İlçe adı, mahalle yaş oranları ilçe düzeyinde aşağı ölçeklendiği için
    # sonradan yapılacak halk sağlığı yakınsaklık kontrollerinde de gerekir.
    roads["ilce_adi"] = joined["ilce_adi"].values
    roads["nufus_yogunlugu"] = joined["nufus_yogunlugu"].values
    roads["yasli_oran"] = joined["yasli_oran"].values
    roads["cocuk_oran"] = joined["cocuk_oran"].values
    if has_sosyoekonomik:
        roads["sosyoekonomik_skor"] = joined["sosyoekonomik_skor"].values

    # --- Sağlığa/yeşil alana uzaklık ve bina yoğunluğu: OSM'den, statik (yıldan bağımsız) ---
    print("Sağlık hizmeti noktaları yükleniyor...")
    health_points = load_health_points(config, pbf_path)
    print(f"  {len(health_points):,} sağlık noktası bulundu")
    print("Yeşil alan poligonları yükleniyor...")
    green_polys = load_green_space_polygons(config, pbf_path)
    print(f"  {len(green_polys):,} yeşil alan poligonu bulundu")
    print("Bina merkez noktaları yükleniyor (yoğunluk için)...")
    building_centroids = load_building_centroids(config, pbf_path)
    print(f"  {len(building_centroids):,} bina bulundu")

    centroid_utm = roads_utm.geometry.centroid
    roads["dist_saglik_m"] = _nearest_distance_m(centroid_utm, health_points, config.crs).round(1)
    roads["dist_yesil_m"] = _nearest_distance_m(centroid_utm, green_polys, config.crs).round(1)

    building_centroids_utm = building_centroids.to_crs(config.crs)
    print(f"Bina yoğunluğu hesaplanıyor ({BUILDING_DENSITY_BUFFER_M} m tampon)...")
    roads["bina_yogunlugu"] = _building_density_per_km2(building_centroids_utm, roads_utm).round(1)
    sifir_oran = (roads["bina_yogunlugu"] == 0).mean()
    print(f"  bina yoğunluğu 0 çıkan yol oranı: %{sifir_oran * 100:.1f}")
    if sifir_oran > 0.25:
        # Dar bir tampon mesafesi bu oranı yapay olarak şişirip geometrik
        # ortalama yüzünden tüm HVI sıralamasını bozabilir; erken uyar.
        print("  UYARI: bu oran beklenenden yüksek - tampon mesafesini "
              "veya OSM bina kapsamını kontrol edin")

    roads = roads.drop(columns=["centroid"])

    # --- Statik (yıldan bağımsız) bileşenlerin normalize değerleri ---
    roads["exposure_norm"] = robust_normalize_0_1(roads["nufus_yogunlugu"])
    roads["sensitivity_yasli_norm"] = robust_normalize_0_1(roads["yasli_oran"])
    roads["sensitivity_cocuk_norm"] = robust_normalize_0_1(roads["cocuk_oran"])
    roads["sensitivity_saglik_norm"] = robust_normalize_0_1(roads["dist_saglik_m"])
    roads["sensitivity_yesil_norm"] = robust_normalize_0_1(roads["dist_yesil_m"])
    roads["sensitivity_yapilasma_norm"] = robust_normalize_0_1(roads["bina_yogunlugu"])

    static_components = [
        "exposure_norm", "sensitivity_yasli_norm", "sensitivity_cocuk_norm",
        "sensitivity_saglik_norm", "sensitivity_yesil_norm", "sensitivity_yapilasma_norm",
    ]

    if has_sosyoekonomik:
        # Skor yüksek = ilçe daha gelişmiş = risk katkısı DÜŞÜK olmalı;
        # bu yüzden riske normalize edilirken skorun TERSİ kullanılır
        # (ağaç örtüsündeki NDVI tersleme deseniyle aynı mantık).
        roads["sensitivity_sosyoekonomik_norm"] = 1 - robust_normalize_0_1(roads["sosyoekonomik_skor"])
        static_components.append("sensitivity_sosyoekonomik_norm")

    # Tüm yollarda aynı değeri alan bileşen (tek ilçeli şehirde ilçe düzeyi
    # demografi) yolları ayırt etmez; grup ortalamasına sabit bir 0 olarak
    # girip diğer üyeleri seyreltmesin diye dışarıda bırakılır. Sütunun
    # kendisi yine de çıktıya yazılır.
    active_static = informative_components(roads, static_components)
    dropped = sorted(set(static_components) - set(active_static))
    if dropped:
        print(f"  Ayırt etmediği için endekse alınmayan bileşenler: {', '.join(dropped)}")

    # --- Yıl bazlı bileşenler: ORTAK ölçekle normalize edilir ---
    # Sıcaklık ve NDVI her yıl kendi aralığına sıkıştırılsaydı, aynı
    # sıcaklık iki yılda farklı bir risk katkısı üretir ve yıl karşılaştırması
    # anlamını yitirirdi. `core/roads.py` LST risk skorunda aynı gerekçeyle
    # ortak ölçek kullanıyor; burada o zincir korunuyor.
    risk_low, risk_high = robust_bounds(pd.concat([roads[f"risk_score_{y}"] for y in years]))
    ndvi_low, ndvi_high = robust_bounds(pd.concat([roads[f"ndvi_mean_{y}"] for y in years]))

    def _scale(series: pd.Series, lo: float, hi: float) -> pd.Series:
        return series * 0 if hi == lo else (series - lo) / (hi - lo)

    values_by_year = {}
    for year in years:
        # Ağaç örtüsü NDVI'nin TERSİ ile riske katkı sağlar: az ağaç = yüksek risk.
        roads[f"hazard_norm_{year}"] = scale_between(roads[f"risk_score_{year}"], risk_low, risk_high)
        roads[f"sensitivity_agac_norm_{year}"] = 1 - scale_between(roads[f"ndvi_mean_{year}"], ndvi_low, ndvi_high)

        values = roads[active_static].copy()
        values["hazard_norm"] = roads[f"hazard_norm_{year}"]
        values["sensitivity_agac_norm"] = roads[f"sensitivity_agac_norm_{year}"]

        # Herhangi bir bileşeni eksik olan yolun skoru NaN'dır. Denetim,
        # endekse alınmayan sabit bileşenleri de kapsar: demografisi eşlenmemiş
        # bir yol, o bileşen ayırt etmiyor diye skor almamalı.
        complete = roads[static_components].notna().all(axis=1) & values.notna().all(axis=1)
        values_by_year[year] = values.where(complete)

    # Grup skorları da yazılır: "bu yol neden yüksek?" sorusu önce grup (sıcak
    # mı, kalabalık mı, kırılgan mı), sonra bileşen düzeyinde yanıtlanabilir.
    group_bounds = pooled_group_bounds(list(values_by_year.values()))
    for year in years:
        groups = rescale_groups(group_scores(values_by_year[year]), group_bounds)
        for group in groups.columns:
            roads[f"group_{group}_{year}"] = groups[group].round(4)
        roads[f"hvi_score_{year}"] = combine_groups(groups)

    # --- Yüzde ve kategori: TÜM yılların ortak dağılımından ---
    # Her yıl kendi içinde 0-100'e ölçeklenseydi, tanım gereği her yılın en
    # kötü yolu %100 çıkar ve "2026'da risk arttı" demek imkansız olurdu.
    # Jenks sınırları da bir kez, birleşik dağılımdan hesaplanır; böylece
    # "Kritik" her iki yılda aynı eşiği ifade eder ve yolların yıllar arası
    # kategori değiştirmesi gerçek bir değişimi gösterir.
    score_all = pd.concat([roads[f"hvi_score_{y}"] for y in years]).dropna()
    score_min, score_max = score_all.min(), score_all.max()

    pct_all = _scale(score_all, score_min, score_max) * 100
    breaks = jenkspy.jenks_breaks(pct_all.to_numpy(), n_classes=5)
    print(f"Ortak Jenks sınırları (tüm yıllar): {[round(b, 1) for b in breaks]}")

    for year in years:
        gecerli = roads[f"hvi_score_{year}"].notna()
        roads.loc[gecerli, f"hvi_percentage_{year}"] = (
            _scale(roads.loc[gecerli, f"hvi_score_{year}"], score_min, score_max) * 100
        )
        roads.loc[gecerli, f"hvi_category_{year}"] = pd.cut(
            roads.loc[gecerli, f"hvi_percentage_{year}"], bins=breaks,
            labels=CATEGORY_ORDER_5, include_lowest=True,
        )
        print(f"[{year}] HVI dağılımı:\n{roads[f'hvi_category_{year}'].value_counts().sort_index()}")

        # Açıklanabilirlik: her bileşen için "yüksek/düşük" gibi doğal-dilde
        # etiket üretilir. Ağaç örtüsü etiketi kasıtlı olarak NDVI'nin
        # KENDİ yönünde (yüksek NDVI = "yüksek ağaç örtüsü") - risk
        # katkısındaki tersleme sadece skor hesabında, kullanıcıya gösterilen
        # metinde değil.
        roads.loc[gecerli, f"_label_sicaklik_{year}"] = bucket_5(
            roads.loc[gecerli, f"risk_score_{year}"], BUCKET_LABELS_5
        ).astype(str)
        roads.loc[gecerli, f"_label_agac_{year}"] = bucket_5(
            roads.loc[gecerli, f"ndvi_mean_{year}"], BUCKET_LABELS_5
        ).astype(str)

    roads["_label_nufus"] = bucket_5(roads["exposure_norm"], BUCKET_LABELS_5_DENSITY).astype(str)
    roads["_label_yasli"] = bucket_5(roads["sensitivity_yasli_norm"], BUCKET_LABELS_5).astype(str)
    roads["_label_cocuk"] = bucket_5(roads["sensitivity_cocuk_norm"], BUCKET_LABELS_5).astype(str)
    roads["_label_saglik"] = bucket_5(roads["sensitivity_saglik_norm"], BUCKET_LABELS_5_DISTANCE).astype(str)
    roads["_label_yesil"] = bucket_5(roads["sensitivity_yesil_norm"], BUCKET_LABELS_5_DISTANCE).astype(str)
    roads["_label_yapilasma"] = bucket_5(roads["sensitivity_yapilasma_norm"], BUCKET_LABELS_5_DENSITY).astype(str)
    if has_sosyoekonomik:
        # Etiket kasıtlı olarak skorun KENDİ yönünde ("yüksek" = gelişmiş
        # ilçe) - risk katkısındaki tersleme sadece skor hesabında.
        roads["_label_sosyoekonomik"] = bucket_5(normalize_0_1(roads["sosyoekonomik_skor"]), BUCKET_LABELS_5).astype(str)

    for year in years:
        roads[f"hvi_category_{year}"] = roads[f"hvi_category_{year}"].astype(str)

    roads.to_file(output_path, driver="GeoJSON")
    write_cache_meta(output_path, HVI_FORMULA_VERSION)
    print(f"Kaydedildi: {output_path.name} ({len(roads):,} yol segmenti)")
    return roads
