"""Birden fazla şehri sırayla üretir: pipeline, veri paketi ve özet durum dosyası.

    python tools/batch_cities.py                 # İzmir dışındaki tüm şehirler
    python tools/batch_cities.py eskisehir adana # yalnızca verilenler
    python tools/batch_cities.py --keep-raw      # Landsat pencerelerini silme

Her şehir ayrı bir süreçte çalışır: 8 GB RAM'lik bir makinede bir şehrin
belleği bir sonrakine taşınmaz. Aynı bölgesel OSM özütünü kullanan şehirler
özütü bir kez indirir (`data/raw/_bolgeler/`), şehir klasörüne sabit bağlantı
(hardlink) olarak konur. Başarısız bir şehir işi durdurmaz; durumu
`output/toplu_uretim_durumu.json` dosyasına yazılır ve sonraki çalıştırmada
yalnızca eksik şehirler denenir (`--retry-done` hepsini yeniden dener).

Şehir tamamlanınca Landsat sahne pencereleri silinir (mozaikler ve işlenmiş
çıktılar kalır); pipeline'ın sahne önbelleği bu yüzden bir sonraki
çalıştırmada geçersiz sayılır ve pencereler yeniden okunur. Yerden tasarruf,
70 şehirde yeniden okuma maliyetinden daha önemlidir.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.cache import atomic_output_path  # noqa: E402
from core.city_config import CITIES_DIR, load_city_config  # noqa: E402
from core.paths import OUTPUT_DIR, city_data_raw, resolve_pbf_path  # noqa: E402

REGION_DIR = ROOT / "data" / "raw" / "_bolgeler"
STATUS_PATH = OUTPUT_DIR / "toplu_uretim_durumu.json"
YEARS = ["2020", "2026"]
MAIN_YEAR = "2026"


def _load_status() -> dict:
    if STATUS_PATH.exists():
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output_path(STATUS_PATH) as temporary:
        temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_region_extract(url: str) -> Path:
    """Bölgesel özütü bir kez indirir; boyutu Content-Length ile doğrular.

    Kısmi indirmeye devam (resume) bilerek yok: özüt sunucuda indirme
    sırasında güncellenirse eski ve yeni parçalar karışıp dosyayı bozar.
    """
    REGION_DIR.mkdir(parents=True, exist_ok=True)
    target = REGION_DIR / url.rsplit("/", 1)[-1]
    if target.exists() and target.stat().st_size > 0:
        return target
    print(f"Bölgesel özüt indiriliyor: {url}", flush=True)
    with requests.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        expected = int(response.headers.get("Content-Length", 0))
        with atomic_output_path(target) as temporary, open(temporary, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                handle.write(chunk)
            handle.flush()
            if expected and temporary.stat().st_size != expected:
                raise RuntimeError(f"{url}: {temporary.stat().st_size} bayt indi, {expected} bekleniyordu")
    return target


def link_extract(city_id: str, extract: Path) -> None:
    pbf = resolve_pbf_path(city_id)
    if pbf.exists():
        return
    pbf.parent.mkdir(parents=True, exist_ok=True)
    os.link(extract, pbf)


def remove_scene_windows(city_id: str) -> None:
    raw = city_data_raw(city_id)
    for year_dir in [raw, *[raw / y for y in YEARS]]:
        if not year_dir.is_dir():
            continue
        for scene in year_dir.glob("L[CT]0*_L2SP_*"):
            shutil.rmtree(scene, ignore_errors=True)


def run_city(city_id: str, keep_raw: bool) -> dict:
    config = load_city_config(city_id)
    started = time.time()
    link_extract(city_id, ensure_region_extract(config.osm_pbf_url))
    log_path = OUTPUT_DIR / "toplu_uretim_loglari" / f"{city_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        result = subprocess.run(
            [sys.executable, "-u", str(ROOT / "pipeline.py"), "--city", city_id, "--years", *YEARS,
             "--main-year", MAIN_YEAR],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False,
        )
    entry = {"status": "ok" if result.returncode == 0 else "hata", "returncode": result.returncode,
             "seconds": round(time.time() - started), "log": str(log_path.relative_to(ROOT)),
             "finished_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    if result.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
        entry["error_tail"] = tail
    elif not keep_raw:
        remove_scene_windows(city_id)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cities", nargs="*", help="Şehir kimlikleri; boşsa İzmir dışındaki tüm şehirler")
    parser.add_argument("--keep-raw", action="store_true", help="Landsat sahne pencerelerini silme")
    parser.add_argument("--retry-done", action="store_true", help="Başarıyla bitmiş şehirleri de yeniden üret")
    args = parser.parse_args()

    cities = args.cities or sorted(
        p.name for p in CITIES_DIR.iterdir() if (p / "config.yaml").exists() and p.name != "izmir"
    )
    status = _load_status()
    for index, city_id in enumerate(cities, 1):
        if status.get(city_id, {}).get("status") == "ok" and not args.retry_done:
            continue
        print(f"[{index}/{len(cities)}] {city_id} başlıyor", flush=True)
        try:
            status[city_id] = run_city(city_id, args.keep_raw)
        except Exception as error:  # noqa: BLE001 - tek şehrin hatası toplu işi durdurmamalı
            status[city_id] = {"status": "hata", "error": f"{type(error).__name__}: {error}"}
        _save_status(status)
        print(f"[{index}/{len(cities)}] {city_id}: {status[city_id]['status']} "
              f"({status[city_id].get('seconds', '?')} sn)", flush=True)

    subprocess.run([sys.executable, str(ROOT / "build_docs_index.py")], cwd=ROOT, check=False)
    done = sum(1 for c in cities if status.get(c, {}).get("status") == "ok")
    print(f"Bitti: {done}/{len(cities)} şehir başarılı. Durum: {STATUS_PATH}")


if __name__ == "__main__":
    main()
