"""Şanlıurfa'ya özel demografi adapter'ı.

Eskişehir'deki gibi, Şanlıurfa Büyükşehir Belediyesi'nin İzmir'inkine
benzer bir CKAN açık veri portalı bulunamadı; bu yüzden nüfus/yaş verisi
TÜİK'in resmi, herkese açık yayınlarından statik referans CSV'ler olarak
alındı (mantık `core/ilce_table_adapter.py`'de ortak, bu dosya sadece
şehre özel kaynak notlarını ve CSV yollarını taşır):

  - `ilce_nufus.csv`: Eyyübiye, Haliliye ve Karaköprü'nün 2025 ADNKS
    toplam nüfusu (TÜİK, Adrese Dayalı Nüfus Kayıt Sistemi).
    **Önemli sınırlama**: yaşlı/çocuk oranı için ilçe bazlı bir TÜİK
    yayını bulunamadı - Şanlıurfa İLİ'nin 2025 geniş yaş grubu dağılımı
    (0-14: 833.584, 15-64: 1.330.030, 65+: 102.186; toplam 2.265.800 =
    il toplamı) her üç ilçeye de aynı şekilde uygulandı (yaşlı %4,51,
    çocuk %36,79). Gerçek ilçe bazlı oran il ortalamasından sapabilir.
    Yaş grubu sayıları TÜİK ADNKS 2025'in bir derleyicisinden
    (nufusune.com) alındı; üç grubun toplamının resmi il toplamına
    eşitliği kontrol edildi.
  - `sege_2022_ilce.csv`: T.C. Sanayi ve Teknoloji Bakanlığı'nın resmi
    SEGE-2022 raporundaki (baka.gov.tr üzerinden erişilen PDF, Şanlıurfa
    tablosu) Karaköprü (Türkiye geneli 232.), Haliliye (304.) ve
    Eyyübiye (688.) skorları - İzmir/Eskişehir'deki dosyayla aynı
    format/kaynak.
  - Nüfus yoğunluğu ilçe bazlı sabit bir değer olarak uygulanıyor
    (ilçe toplam nüfusu / ilçe toplam alanı) - mahalle içi eşitsizlik
    yakalanmaz.

Kentsel çekirdek seçimi: Haliliye/Eyyübiye/Karaköprü'nün idari (OSM
admin_level=6) sınırları, şehrin çok ötesine uzanan geniş bir kırsal/
tarımsal hinterlandı da kapsıyor (Harran ovası yönünde onlarca km) -
`config.yaml`'daki bbox bu yüzden tam idari sınır değil, gerçek kentsel
dokunun (küçük/yoğun mahalleler) kümelendiği alan olarak belirlendi.
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
