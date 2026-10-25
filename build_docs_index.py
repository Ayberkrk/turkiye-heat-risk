"""`docs/` altındaki her şehir için üst seviye bir karşılaştırma sayfası üretir.

Her şehir kendi haritasını `pipeline.py` çalıştığında `docs/<sehir>/stats.json`
içine küçük bir özet olarak yazar (bkz. `core/map_builder.py`). Bu script o
özetleri toplayıp `docs/index.html`'i üretir - ham `roads_with_hvi.geojson`
dosyasına (büyük, gitignore'da) ihtiyaç duymaz, bu yüzden veri indirilmemiş
bir makinede de çalışır.

Kullanım (en az bir şehir için `python pipeline.py --city <sehir>` çalıştıktan sonra):
    python build_docs_index.py
"""

from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.cache import atomic_output_path  # noqa: E402
from core.hvi import HVI_FORMULA_VERSION  # noqa: E402
from core.paths import DOCS_DIR  # noqa: E402

_INVALID_FORMULA_VERSION = "invalid"
_CITY_ID_RE = re.compile(r"^[a-z0-9_]+$")
_REQUIRED_STATS_FIELDS = {
    "city_id", "name", "years", "road_count", "avg_hvi_percentage", "top_risk_mahalle",
}


def _validate_city_stats(city: object, stats_path: Path) -> dict:
    if not isinstance(city, dict):
        raise SystemExit(f"{stats_path}: stats.json kök değeri JSON nesnesi olmalı")
    missing = sorted(_REQUIRED_STATS_FIELDS - city.keys())
    if missing:
        raise SystemExit(f"{stats_path}: zorunlu alanlar eksik: {', '.join(missing)}")

    city_id = city["city_id"]
    if not isinstance(city_id, str) or not _CITY_ID_RE.fullmatch(city_id):
        raise SystemExit(f"{stats_path}: city_id küçük harf, rakam veya '_' içeren güvenli bir kimlik olmalı")
    if city_id != stats_path.parent.name:
        raise SystemExit(f"{stats_path}: city_id ({city_id}) şehir klasörüyle eşleşmiyor")
    if not isinstance(city["name"], str) or not city["name"].strip():
        raise SystemExit(f"{stats_path}: name boş olmayan metin olmalı")
    if not isinstance(city["years"], list) or not city["years"] or not all(
        isinstance(year, str) and year for year in city["years"]
    ):
        raise SystemExit(f"{stats_path}: years boş olmayan metin listesi olmalı")
    road_count = city["road_count"]
    if isinstance(road_count, bool) or not isinstance(road_count, int) or road_count < 0:
        raise SystemExit(f"{stats_path}: road_count negatif olmayan tam sayı olmalı")
    average = city["avg_hvi_percentage"]
    if isinstance(average, bool) or not isinstance(average, (int, float)) or not 0 <= average <= 100:
        raise SystemExit(f"{stats_path}: avg_hvi_percentage 0-100 aralığında bir sayı olmalı")
    if city["top_risk_mahalle"] is not None and not isinstance(city["top_risk_mahalle"], str):
        raise SystemExit(f"{stats_path}: top_risk_mahalle metin veya null olmalı")
    return city


def _load_city_stats() -> list[dict]:
    stats = []
    if not DOCS_DIR.exists():
        return stats
    for stats_path in sorted(DOCS_DIR.glob("*/stats.json")):
        try:
            city = json.loads(stats_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SystemExit(f"{stats_path}: stats.json okunamadı: {error}") from error
        city = _validate_city_stats(city, stats_path)
        city["formula_version"] = _formula_version(stats_path.parent)
        stats.append(city)
    return stats


def _formula_version(city_dir: Path) -> int | str | None:
    """Şehrin haritasının hangi HVI formül sürümüyle üretildiğini döndürür.

    Manifest'i olmayan (manifest eklenmeden önce üretilmiş) harita için None.
    """
    manifest_path = city_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = manifest.get("versions", {}).get("hvi_formula_version")
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return _INVALID_FORMULA_VERSION
    if version is None:
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        return _INVALID_FORMULA_VERSION
    return version


def _is_current(stats: dict) -> bool:
    return stats.get("formula_version") == HVI_FORMULA_VERSION


def _city_card(stats: dict) -> str:
    years = ", ".join(escape(year) for year in stats["years"])
    top_mahalle = stats.get("top_risk_mahalle") or "Bilinmiyor"
    city_id = quote(stats["city_id"], safe="_")
    city_name = escape(stats["name"])
    top_mahalle = escape(top_mahalle)
    # Formül değiştiğinde tüm şehirler aynı anda yeniden üretilmeyebilir.
    # Sürümü bilinmeyen eski haritaları da işaretle ama yanlışlıkla eski
    # formül kullanıldığını ileri sürme.
    formula_version = stats.get("formula_version")
    if _is_current(stats):
        status = ""
    elif formula_version is None:
        status = '<p class="eski">Formül sürümü kayıtlı değil; güncelliği bilinmiyor</p>'
    elif formula_version == _INVALID_FORMULA_VERSION:
        status = '<p class="eski">Manifest okunamıyor veya formül sürümü geçersiz</p>'
    else:
        status = '<p class="eski">Eski formülle üretildi, yenilenecek</p>'
    return f"""
    <a class="kart" href="./{city_id}/index.html">
        <h2>{city_name}</h2>
        {status}
        <div class="istatistik"><b>{stats['avg_hvi_percentage']:.1f}</b><span>ortalama HVI yüzdesi</span></div>
        <p>{stats['road_count']:,} yol segmenti · {years}</p>
        <p>En riskli mahalle: <b>{top_mahalle}</b></p>
    </a>
    """.strip()


def build_index() -> Path:
    cities = _load_city_stats()
    if not cities:
        raise SystemExit(
            "docs/ altında hiçbir şehir bulunamadı. Önce en az bir şehir için "
            "`python pipeline.py --city <sehir>` çalıştırın."
        )

    # Güncel formülle üretilenler önce; yüzdeler şehirler arasında
    # karşılaştırılamadığı için sıralama ada göredir, skora göre değil.
    cities.sort(key=lambda c: (not _is_current(c), c["name"]))
    cards_html = "\n".join(_city_card(c) for c in cities)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Kentsel Isı Hassasiyeti - Şehirler</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #1a1a1a; color: #eee; margin: 0; padding: 40px 20px; }}
  h1 {{ text-align: center; font-weight: 600; }}
  p.aciklama {{ text-align: center; color: #aaa; max-width: 640px; margin: 0 auto 40px; }}
  .kartlar {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; max-width: 900px; margin: 0 auto; }}
  .kart {{ display: block; width: 260px; background: #262626; border-radius: 10px; padding: 20px;
           text-decoration: none; color: inherit; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
           transition: transform 0.15s; }}
  .kart:hover {{ transform: translateY(-4px); }}
  .kart h2 {{ margin: 0 0 12px; font-size: 18px; }}
  .istatistik {{ display: flex; align-items: baseline; gap: 6px; margin-bottom: 10px; }}
  .istatistik b {{ font-size: 28px; color: #fd8d3c; }}
  .istatistik span {{ font-size: 12px; color: #aaa; }}
  .kart p {{ font-size: 13px; color: #ccc; margin: 4px 0; }}
  .kart p.eski {{ color: #fdae6b; font-size: 12px; margin: -6px 0 10px; }}
</style>
</head>
<body>
<h1>Kentsel Isı Hassasiyeti Endeksi (HVI)</h1>
<p class="aciklama">Yüzey sıcaklığını (tehlike), nüfus ve yapılaşma
yoğunluğunu (maruziyet), yaş, sosyoekonomik durum, sağlık ve yeşil alan
erişimini (kırılganlık) birleştiren bir önceliklendirme endeksi. Bir şehre
tıklayarak yol bazlı interaktif haritayı açabilirsiniz.</p>
<p class="aciklama">Skorlar her şehrin kendi içinde ölçeklenir: yüzdeler bir
şehrin içindeki yolları sıralar, şehirleri birbiriyle karşılaştırmaz.</p>
<div class="kartlar">
{cards_html}
</div>
</body>
</html>
""".strip() + "\n"
    DOCS_DIR.mkdir(exist_ok=True)
    index_path = DOCS_DIR / "index.html"
    with atomic_output_path(index_path) as temporary:
        temporary.write_text(html, encoding="utf-8")
    print(f"Kaydedildi: {index_path} ({len(cities)} şehir)")
    return index_path


if __name__ == "__main__":
    build_index()
