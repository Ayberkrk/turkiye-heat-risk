"""Eskişehir'e özel demografi adapter'ı.

İzmir'in aksine Eskişehir Büyükşehir Belediyesi'nin kendi CKAN açık veri
portalı yok; bu yüzden nüfus/yaş verisi TÜİK'in resmi, herkese açık
yayınlarından statik referans CSV'ler olarak alındı (mantık
`core/ilce_table_adapter.py`'de ortak, bu dosya sadece şehre özel kaynak
notlarını ve CSV yollarını taşır):

  - `ilce_nufus.csv`: Odunpazarı ve Tepebaşı'nın 2025 ADNKS toplam nüfusu
    (TÜİK, Adrese Dayalı Nüfus Kayıt Sistemi) ve yaşlı/çocuk oranı.
    **Önemli sınırlama**: yaşlı/çocuk oranı için ilçe bazlı bir TÜİK
    yayını bulunamadı - bu yüzden Eskişehir İLİ'nin 2025 geniş yaş grubu
    dağılımı (0-14: 149.481, 15-64: 651.145, 65+: 127.330; toplam 927.956
    = il toplamı) her iki ilçeye de aynı şekilde uygulandı (çocuk %16,11,
    yaşlı %13,72). İzmir adapter'ı yaş oranını ilçe seviyesinde uyguluyordu
    (mahalle seviyesinde değil); burada bir kademe daha kaba bir yaklaşım
    kullanılıyor (il seviyesi). Gerçek ilçe bazlı oran, il ortalamasından
    belirgin şekilde sapabilir. Yaş grubu sayıları TÜİK ADNKS 2025'in bir
    derleyicisinden (nufusune.com) alındı; üç grubun toplamının resmi il
    toplamına eşitliği kontrol edildi.
  - `sege_2022_ilce.csv`: T.C. Sanayi ve Teknoloji Bakanlığı'nın resmi
    SEGE-2022 raporundaki Odunpazarı (Türkiye geneli 48.) ve Tepebaşı
    (84.) skorları - İzmir'deki dosyayla aynı format/kaynak.
  - Nüfus yoğunluğu da ilçe bazlı sabit bir değer olarak uygulanıyor
    (ilçe toplam nüfusu / ilçe toplam alanı) - mahalle bazlı gerçek nüfus
    dağılımı olmadığı için her mahalle aynı yoğunluğu alır. Bu, gerçek
    mahalle-içi eşitsizliği (ör. bir mahallenin çok daha yoğun olması)
    gizler; İzmir'in mahalle bazlı CKAN nüfus verisiyle mümkün olan
    çözünürlük burada yok.

Bu sınırlamalar bilinçli bir tercih: TÜİK verisi Türkiye'deki her il/ilçe
için mevcut, bu yüzden bu adapter (İzmir'in CKAN'a özel adapter'ının
aksine) İzmir'inkine benzer bir belediye açık veri portalı olmayan
HERHANGİ bir Türkiye şehrine kolayca uyarlanabilir bir şablon oluşturuyor.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from core.city_config import CityConfig
from core.ilce_table_adapter import build_neighborhood_layer_from_ilce_tables

_CITY_DIR = Path(__file__).resolve().parent
ILCE_NUFUS_CSV_PATH = _CITY_DIR / "ilce_nufus.csv"
SEGE_CSV_PATH = _CITY_DIR / "sege_2022_ilce.csv"


def fetch_population_data(config: CityConfig) -> dict[str, Path]:
    """Nüfus verisi statik referans CSV olarak repoyla birlikte geldiği için
    indirilecek bir şey yok - arayüz uyumluluğu için boş sözlük döner.
    """
    return {}


def build_neighborhood_layer(pbf_path: Path, population_paths: dict[str, Path], config: CityConfig) -> gpd.GeoDataFrame:
    return build_neighborhood_layer_from_ilce_tables(pbf_path, config, ILCE_NUFUS_CSV_PATH, SEGE_CSV_PATH)
