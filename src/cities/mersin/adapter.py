"""Mersin'a özel demografi adapter'ı.

Mersin için de belediye CKAN'ından mahalle düzeyinde nüfus/yaş verisi
kullanılmıyor; Eskişehir/Şanlıurfa'daki TÜİK-statik-CSV şablonu uygulandı
(mantık `core/ilce_table_adapter.py`'de ortak, bu dosya sadece şehre özel
kaynak notlarını ve CSV yollarını taşır):

  - `ilce_nufus.csv`: Yenişehir, Akdeniz, Mezitli, Toroslar ilçelerinin 2025 ADNKS toplam nüfusu.
    Tüm il ilçelerinin nüfus toplamı resmi il toplamına (1.956.428) eşit çıktı
    (ilçe rakamlarının doğrulanması). **Önemli sınırlama**: yaşlı/çocuk
    oranı için ilçe bazlı bir TÜİK yayını bulunamadı - Mersin İLİ'nin 2025
    geniş yaş grubu dağılımı (0-14: 403.300, 65+: 224.825; 15-64 ile toplamı il
    toplamına eşit) her ilçeye aynı şekilde uygulandı (çocuk %20,61, yaşlı
    %11,49). Gerçek ilçe bazlı oran il ortalamasından sapabilir. Yaş grubu
    sayıları TÜİK ADNKS 2025'in bir derleyicisinden (nufusune.com) alındı.
  - `sege_2022_ilce.csv`: T.C. Sanayi ve Teknoloji Bakanlığı'nın resmi
    SEGE-2022 raporundaki (baka.gov.tr üzerinden erişilen PDF, Mersin
    tablosu) Yenişehir (Türkiye geneli 49.), Akdeniz (103.), Mezitli (107.) ve Toroslar (240.) skorları.
  - Nüfus yoğunluğu ilçe bazlı sabit bir değer olarak uygulanıyor
    (ilçe toplam nüfusu / ilçe toplam alanı) - mahalle içi eşitsizlik
    yakalanmaz. Ayrıca ilçe alanı OSM idari sınırından hesaplandığı için
    kırsal hinterlandı geniş ilçelerde yoğunluk bbox'taki gerçek kentsel
    dokuya göre düşük çıkar.

Doğrulama: gerçek OSM özütüyle (83 mahalle, 14.472 yol segmenti) `validate_city.py` ve
`build_neighborhood_layer` çalıştırıldı, bkz. CHANGELOG.
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
