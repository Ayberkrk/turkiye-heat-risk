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
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.hvi import HVI_FORMULA_VERSION  # noqa: E402
from core.paths import DOCS_DIR  # noqa: E402


def _load_city_stats() -> list[dict]:
    stats = []
    if not DOCS_DIR.exists():
        return stats
    for stats_path in sorted(DOCS_DIR.glob("*/stats.json")):
        city = json.loads(stats_path.read_text())
        city["formula_version"] = _formula_version(stats_path.parent)
        stats.append(city)
    return stats


def _formula_version(city_dir: Path) -> int | None:
    """Şehrin haritasının hangi HVI formül sürümüyle üretildiğini döndürür.

    Manifest'i olmayan (manifest eklenmeden önce üretilmiş) harita için None.
    """
    manifest_path = city_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text()).get("versions", {}).get("hvi_formula_version")


def _is_current(stats: dict) -> bool:
    return stats.get("formula_version") == HVI_FORMULA_VERSION


def _city_card(stats: dict) -> str:
    years = ", ".join(stats["years"])
    top_mahalle = stats.get("top_risk_mahalle") or "Bilinmiyor"
    # Formül değiştiğinde her şehir aynı anda yeniden üretilmeyebilir; eski
    # formülle kalan harita güncel olanlarla aynı sayfada işaretsiz durmamalı.
    stale = "" if _is_current(stats) else '<p class="eski">Eski formülle üretildi, yenilenecek</p>'
    return f"""
    <a class="kart" href="./{stats['city_id']}/index.html">
        <h2>{stats['name']}</h2>
        {stale}
        <div class="istatistik"><b>{stats['avg_hvi_percentage']:.1f}</b><span>ortalama HVI yüzdesi</span></div>
        <p>{stats['road_count']:,} yol segmenti · {years}</p>
        <p>En riskli mahalle: <b>{top_mahalle}</b></p>
    </a>
    """


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
"""
    DOCS_DIR.mkdir(exist_ok=True)
    index_path = DOCS_DIR / "index.html"
    index_path.write_text(html, encoding="utf-8")
    print(f"Kaydedildi: {index_path} ({len(cities)} şehir)")
    return index_path


if __name__ == "__main__":
    build_index()
