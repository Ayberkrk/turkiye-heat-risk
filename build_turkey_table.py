"""Üretilmiş tüm şehirlerin veri paketlerinden Türkiye geneli tablolar oluşturur.

    python build_turkey_table.py

Girdi: `output/<şehir>/paket/<şehir>_mahalleler.csv` ve `..._ilceler.csv`
(pipeline.py ya da export_city.py yazar). Çıktı `docs/veri/` altında:

  - `turkiye_mahalleler.csv`: tüm şehirlerin mahalle satırları, `sehir` sütunuyla.
  - `turkiye_sehirler.csv`: şehir başına bir satır.
  - `turkiye_isi_riski.xlsx`: ikisi ve bir "Okuyun" sayfası.

**Şehirler arası karşılaştırma uyarısı.** HVI ve kategoriler her şehrin kendi
dağılımına göre ölçeklenir: İzmir'de 80 olan bir mahalle ile Sivas'ta 80 olan
bir mahalle aynı mutlak riski taşımaz. Tablo bu yüzden iki tür sütun taşır:
şehir içi göreli olanlar (`hvi_*`, `sira`, `yuksek_risk_payi_*`) ve şehirler
arasında doğrudan karşılaştırılabilen mutlak ölçümler (yüzey sıcaklığı °C,
NDVI, kişi/km², yaş oranları, mesafeler). Şehirler arası bir sıralama
yapılacaksa yalnızca ikinci gruba dayanılmalıdır.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from core.cache import atomic_output_path  # noqa: E402
from core.city_config import CITIES_DIR, load_city_config  # noqa: E402
from core.export import DISCLAIMER, SOURCES, write_workbook  # noqa: E402
from core.paths import DOCS_DIR, OUTPUT_DIR  # noqa: E402

RELATIVE_NOTE = (
    "hvi_*, sira ve yuksek_risk_payi_* sütunları şehir içi görelidir; şehirler arası karşılaştırmada "
    "yalnızca lst_ort_* (°C), ndvi_ort_*, nufus_yogunlugu (kişi/km²), yaş oranları ve mesafeler kullanılmalıdır."
)


def _km_weighted(frame: pd.DataFrame, column: str) -> float | None:
    """Mahalle değerlerinin yol uzunluğuyla ağırlıklı ortalaması (şehrin yol ortalamasına yakın)."""
    if column not in frame:
        return None
    valid = frame[column].notna() & frame["toplam_yol_km"].notna()
    weights = frame.loc[valid, "toplam_yol_km"]
    return round(float((frame.loc[valid, column] * weights).sum() / weights.sum()), 3)


def collect(output_dir: Path = OUTPUT_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    mahalle_parts, city_rows = [], []
    for city_dir in sorted(p for p in CITIES_DIR.iterdir() if (p / "config.yaml").exists()):
        city_id = city_dir.name
        mahalle_csv = output_dir / city_id / "paket" / f"{city_id}_mahalleler.csv"
        if not mahalle_csv.exists():
            continue
        config = load_city_config(city_id)
        mahalle = pd.read_csv(mahalle_csv)
        mahalle.insert(0, "sehir", config.name)
        mahalle.insert(1, "sehir_kimligi", city_id)
        mahalle_parts.append(mahalle)
        main_year = max(int(c.rsplit("_", 1)[1]) for c in mahalle.columns if c.startswith("hvi_ort_"))
        reliable = mahalle[mahalle["guvenilir_ortalama"] == "Evet"]
        top = (reliable if len(reliable) else mahalle).iloc[0]
        lst_last = _km_weighted(mahalle, f"lst_ort_{main_year}")
        lst_first = _km_weighted(mahalle, "lst_ort_2020") if main_year != 2020 else None

        city_rows.append({
            "sehir": config.name, "sehir_kimligi": city_id,
            "mahalle_sayisi": int(len(mahalle)), "ilce_sayisi": int(mahalle["ilce_adi"].nunique()),
            "yol_sayisi": int(mahalle["yol_sayisi"].sum()), "toplam_yol_km": round(float(mahalle["toplam_yol_km"].sum()), 1),
            f"lst_ort_{main_year}": lst_last,
            f"ndvi_ort_{main_year}": _km_weighted(mahalle, f"ndvi_ort_{main_year}"),
            "lst_degisim": round(lst_last - lst_first, 3) if lst_last is not None and lst_first is not None else None,
            "en_riskli_mahalle": f"{top['mahalle_adi']} ({top['ilce_adi']})",
            "demografi_ilce_ici_sabit": bool(mahalle["ilce_adi"].nunique() == 1),
        })
    if not mahalle_parts:
        raise SystemExit("output/<şehir>/paket/ altında hiç veri paketi yok; önce pipeline.py çalıştırın.")
    return pd.concat(mahalle_parts, ignore_index=True), pd.DataFrame(city_rows)


def build(output_dir: Path = OUTPUT_DIR, target: Path = DOCS_DIR / "veri") -> Path:
    mahalle, cities = collect(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    with atomic_output_path(target / "turkiye_mahalleler.csv") as temporary:
        mahalle.to_csv(temporary, index=False)
    with atomic_output_path(target / "turkiye_sehirler.csv") as temporary:
        cities.to_csv(temporary, index=False)
    readme = pd.DataFrame([("Önemli", DISCLAIMER), ("Şehirler arası karşılaştırma", RELATIVE_NOTE),
                           ("Sütunların anlamı", "Her şehrin veri paketindeki sutun_sozlugu.csv ile aynı.")],
                          columns=["Başlık", "Açıklama"])
    write_workbook(target / "turkiye_isi_riski.xlsx", {
        "Okuyun": readme, "Şehirler": cities, "Mahalleler": mahalle,
        "Kaynaklar ve lisans": pd.DataFrame(SOURCES, columns=["Veri", "Kaynak", "Lisans"]),
    })
    print(f"{len(cities)} şehir, {len(mahalle):,} mahalle: {target}")
    return target


if __name__ == "__main__":
    build()
