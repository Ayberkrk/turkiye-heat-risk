"""Bir şehrin bbox'ını gerçek OSM sınırlarından, yoğun mahalle kümesine göre çizer.

Neden: bir ilçenin idari sınırı kent merkezinden çok daha büyük olabilir
(kırsal hinterland), bbox'ı ilçenin tamamından ya da elle yazılmış bir
koordinat karesinden almak yanlış yeri analiz eder ya da hiç eşleşmez
(bkz. CONTRIBUTING.md). Yöntem, projenin her şehirde elle uyguladığı adımdır:

  1. Şehrin `ilce_nufus.csv`'sindeki ilçeleri OSM idari sınırlarında bul
     ("Merkez" satırı, OSM'de "<İl> Merkez" adını taşır).
  2. O ilçelerin mahallelerinden küçük/yoğun olanları (< 3 km2) seç; bunlar
     gerçek kentsel dokunun göstergesidir. Uzaktaki tek tük köy mahallelerini ayıkla.
  3. bbox = bu kümenin sınırları (biraz payla). UTM dilimi bbox merkezinden gelir.
  4. Sonucu GERÇEK OSM ile ölç: bbox'taki yolların kaçı demografisi eşlenmiş
     bir mahalleye düşüyor (`core/coverage.py`).

Kullanım (OSM bölge özütleri `--pbf-dir` altında `<bolge>.osm.pbf` adıyla):
    python tools/fit_city_bbox.py burdur isparta --pbf-dir data/raw/_bolgeler
    python tools/fit_city_bbox.py --all --pbf-dir data/raw/_bolgeler --json sonuc.json
    python tools/fit_city_bbox.py burdur --pbf-dir ... --apply    # config.yaml'ı günceller
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from core.city_config import CITIES_DIR, CityConfig, load_city_config  # noqa: E402
from core.coverage import measure_city_coverage  # noqa: E402
from core.ilce_table_adapter import is_merkez_key  # noqa: E402
from core.text_utils import normalize_name  # noqa: E402

DENSE_KM2 = 3.0          # bunun altındaki mahalleler kentsel doku sayılır
MIN_DENSE = 5            # bundan az yoğun mahalle varsa en küçük 8'i al
FALLBACK_N = 8
CLUSTER_MIN_DEG = 0.10   # ~10 km: kümenin merkezinden bu kadar uzaktaki mahalleleri ayıkla
CLUSTER_MAX_DEG = 0.18   # hiçbir zaman bundan uzağı alma (bbox'ı makul tutar)
PAD_DEG = 0.005
SEARCH_RADII = (0.3, 0.6)
GOOD_COVERAGE = 0.85     # tam bbox bu kapsamı sağlıyorsa sıkı çekirdek denenmez


def _utm_epsg(lon: float) -> str:
    return f"EPSG:326{int((lon + 180) // 6) + 1:02d}"


def _key(name) -> str:
    return normalize_name(name) if isinstance(name, str) else ""


def _read_admin(pbf: Path, bbox: tuple) -> gpd.GeoDataFrame:
    return gpd.read_file(pbf, layer="multipolygons", bbox=bbox,
                         columns=["name", "admin_level", "boundary", "geometry"], on_invalid="ignore")


def _pick_target_ilce(ilce: gpd.GeoDataFrame, csv_names: list[str], il_adi: str, anchor) -> tuple[list, list[str]]:
    """CSV'deki her ilçe için OSM poligonunu seçer; bulunamayanları ayrıca döner."""
    ilce = ilce.assign(key=ilce["name"].map(_key))
    picked, missing = [], []
    for csv_name in csv_names:
        key = _key(csv_name)
        cands = ilce[ilce["key"] == key]
        if cands.empty and is_merkez_key(key):
            # Merkez ilçe OSM'de "<İl> Merkez" ya da düz "Merkez" yazılmış olabilir:
            # önce il adıyla eşleşeni, sonra düz "Merkez"i dene. Başka ilin "<İl> Merkez"ine
            # düşmemek için herhangi bir merkez-türüne geri dönülmez.
            for aday in (_key(il_adi) + " MERKEZ", "MERKEZ"):
                cands = ilce[ilce["key"] == aday]
                if not cands.empty:
                    break
        if cands.empty:
            missing.append(csv_name)
            continue
        if len(cands) > 1:  # aynı ad birden fazla ilde olabilir (ör. "Merkez"): çapaya en yakın olan
            dist = cands.geometry.centroid.distance(anchor)
            cands = cands.loc[[dist.idxmin()]]
        picked.append(cands.iloc[0])
    return picked, missing


def fit_bbox(config: CityConfig, pbf: Path) -> dict:
    """bbox adayını çizer ve gerçek OSM kapsamıyla ölçer. Bulunamazsa `hata` döner."""
    csv = pd.read_csv(config.config_dir / "ilce_nufus.csv", sep=";", encoding="utf-8")
    csv_names = list(csv["ILCE"])
    w, s, e, n = config.bbox
    anchor = gpd.GeoSeries.from_xy([(w + e) / 2], [(s + n) / 2]).iloc[0]

    picked, missing = [], csv_names
    admin = _read_admin(pbf, (anchor.x - SEARCH_RADII[0], anchor.y - SEARCH_RADII[0] * 0.8,
                              anchor.x + SEARCH_RADII[0], anchor.y + SEARCH_RADII[0] * 0.8))
    for i, radius in enumerate(SEARCH_RADII):
        if i:  # ilk yarıçap yukarıda okundu; sonuç bulunamazsa genişlet
            admin = _read_admin(pbf, (anchor.x - radius, anchor.y - radius * 0.8, anchor.x + radius, anchor.y + radius * 0.8))
        ilce = admin[(admin["admin_level"] == config.admin_level_ilce) & (admin["boundary"] == "administrative")]
        picked, missing = _pick_target_ilce(ilce, csv_names, config.name, anchor)
        if not missing:
            break
    if not picked:
        return {"hata": f"CSV ilçeleri OSM'de bulunamadı: {missing}"}

    targets = gpd.GeoDataFrame(picked, crs="EPSG:4326")
    tb = targets.total_bounds
    mah = admin[(admin["admin_level"] == config.admin_level_mahalle) & (admin["boundary"] == "administrative")]
    if not (mah.total_bounds[0] <= tb[0] and mah.total_bounds[2] >= tb[2]):  # arama kutusu ilçeyi kapsamıyorsa yeniden oku
        mah = _read_admin(pbf, (tb[0] - 0.01, tb[1] - 0.01, tb[2] + 0.01, tb[3] + 0.01))
        mah = mah[(mah["admin_level"] == config.admin_level_mahalle) & (mah["boundary"] == "administrative")]

    utm = _utm_epsg((tb[0] + tb[2]) / 2)
    cent = mah.to_crs(utm).geometry.centroid.to_crs("EPSG:4326")
    mah = mah.assign(cx=cent.x.values, cy=cent.y.values, alan=(mah.to_crs(utm).geometry.area / 1e6).values)
    inside = gpd.GeoSeries.from_xy(mah["cx"], mah["cy"], crs="EPSG:4326").within(targets.union_all())
    mah = mah[inside.values]
    if mah.empty:
        return {"hata": "hedef ilçelerde mahalle bulunamadı"}

    dense = mah[mah["alan"] < DENSE_KM2]
    if len(dense) < MIN_DENSE:
        dense = mah.nsmallest(FALLBACK_N, "alan")
    mx, my = dense["cx"].median(), dense["cy"].median()
    d = np.hypot(dense["cx"] - mx, dense["cy"] - my)
    kept = dense[d <= min(CLUSTER_MAX_DEG, max(CLUSTER_MIN_DEG, 2.5 * d.median()))]

    def _box(sel: gpd.GeoDataFrame, quantile: bool) -> list[float]:
        if quantile and len(sel) >= 6:  # uç mahalleleri kırp: daha sıkı çekirdek
            lo, hi = sel["cx"].quantile(0.1), sel["cx"].quantile(0.9)
            lo_y, hi_y = sel["cy"].quantile(0.1), sel["cy"].quantile(0.9)
            b = [lo - 0.01, lo_y - 0.01, hi + 0.01, hi_y + 0.01]
        else:
            tb2 = sel.total_bounds
            b = [tb2[0] - PAD_DEG, tb2[1] - PAD_DEG, tb2[2] + PAD_DEG, tb2[3] + PAD_DEG]
        return [math.floor(b[0] * 100) / 100, math.floor(b[1] * 100) / 100,
                math.ceil(b[2] * 100) / 100, math.ceil(b[3] * 100) / 100]

    best: dict = {}
    for variant, quantile in (("tam", False), ("cekirdek", True)):
        bbox = _box(kept, quantile)
        cfg2 = dataclasses.replace(config, bbox=bbox, crs=_utm_epsg((bbox[0] + bbox[2]) / 2))
        res = measure_city_coverage(cfg2, pbf)
        res.update(bbox=bbox, crs=cfg2.crs, varyant=variant, hedef_ilce=[p["name"] for p in picked],
                   eksik_ilce=missing, yogun_mahalle=len(kept))
        if not best or res["coverage"] > best["coverage"] + 0.02:
            best = res
        # Geniş (tam) bbox zaten yeterince kapsıyorsa daha büyük alanı koru; sıkı
        # çekirdeğe yalnızca kapsam düşükse (komşu ilçe taşması) başvur.
        if variant == "tam" and res["coverage"] >= GOOD_COVERAGE:
            break
    return best


def _apply(city_id: str, result: dict) -> None:
    p = CITIES_DIR / city_id / "config.yaml"
    text = p.read_text(encoding="utf-8")
    bbox = ", ".join(f"{v:.2f}" for v in result["bbox"])
    note = (f"  # bbox: tools/fit_city_bbox.py ile yoğun mahalle kümesinden çizildi ({result['varyant']}); "
            f"gerçek OSM'de HVI kapsamı %{result['coverage'] * 100:.0f} ({result['yol']:,} yol).")
    text, _ = re.subn(r"^  # bbox: tools/fit_city_bbox\.py.*\n", "", text, flags=re.M)  # eski notu tekrarlama
    text, n2 = re.subn(r"^  bbox: \[.*?\](.*)$", lambda m: f"{note}\n  bbox: [{bbox}]{m.group(1)}", text, count=1, flags=re.M)
    text, n3 = re.subn(r'^  crs: ".*?"', f'  crs: "{result["crs"]}"', text, count=1, flags=re.M)
    if not (n2 and n3):
        raise RuntimeError(f"{city_id}: config.yaml'da bbox/crs satırı bulunamadı")
    p.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cities", nargs="*", help="şehir kimlikleri")
    ap.add_argument("--all", action="store_true", help="ilce_nufus.csv taşıyan tüm şehirler")
    ap.add_argument("--pbf-dir", type=Path, required=True, help="<bolge>.osm.pbf dosyalarının dizini")
    ap.add_argument("--json", type=Path, help="sonuçları JSON olarak yaz")
    ap.add_argument("--apply", action="store_true", help="bulunan bbox/crs'i config.yaml'a yaz")
    ap.add_argument("--regions", nargs="*", help="yalnızca bu OSM bölgelerindeki şehirler (--all ile)")
    args = ap.parse_args()

    ids = args.cities or []
    if args.all:
        ids = sorted(p.name for p in CITIES_DIR.iterdir() if (p / "ilce_nufus.csv").exists())
    out = {}
    for cid in ids:
        cfg = load_city_config(cid)
        region_m = re.search(r"turkey/(.+?)-latest", cfg.osm_pbf_url)
        region = region_m.group(1) if region_m else ""
        if args.regions and region not in args.regions:
            continue
        pbf = args.pbf_dir / f"{region}.osm.pbf"
        try:
            res = fit_bbox(cfg, pbf)
        except Exception as exc:  # tek şehrin hatası toplu çalışmayı durdurmasın
            res = {"hata": f"{type(exc).__name__}: {str(exc)[:120]}"}
        out[cid] = res
        if "hata" in res:
            print(f"{cid:15s} HATA: {res['hata']}", flush=True)
            continue
        print(f"{cid:15s} kapsam=%{res['coverage'] * 100:5.1f} yol={res['yol']:6d} mahalle={res['mahalle']:4d} "
              f"bbox={res['bbox']} {res['crs']} ({res['varyant']}) ilce={res['ilce']}", flush=True)
        if args.apply:
            _apply(cid, res)
        if args.json:  # her şehirden sonra yaz: uzun çalışma yarıda kesilse de sonuç kalsın
            args.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
