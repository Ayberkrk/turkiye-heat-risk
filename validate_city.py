"""Yeni bir şehir config.yaml'ının temel doğruluğunu kontrol eder.

Kullanım:
    python validate_city.py <sehir> [--osm-coverage [--pbf DOSYA] [--min-coverage 0.6]]

Kontrol ettikleri:
  1. `src/cities/<sehir>/config.yaml` var mı ve gerekli tüm alanları içeriyor mu
  2. bbox [batı, güney, doğu, kuzey] biçiminde ve koordinatlar geçerli mi
  3. Adapter modülü import edilebiliyor mu ve gerekli iki fonksiyonu
     (`fetch_population_data`, `build_neighborhood_layer`) uyguluyor mu
  4. OSM `.pbf` adresi erişilebilir mi
  5. Nüfus veri kaynağı (CKAN vb.) gerçekten erişilebilir mi (varsa)
  6. (`--osm-coverage` ile) bbox'taki yolların yeterli payı, gerçek OSM
     sınırlarıyla demografisi eşlenmiş bir mahalleye düşüyor mu

Bu script hiçbir veri indirmez/işlemez - sadece config'in "çalışmaya hazır"
olup olmadığını hızlıca doğrular. Tam bir doğrulama için pipeline.py'ı
gerçekten çalıştırmak gerekir.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import requests  # noqa: E402

from core.city_config import CITIES_DIR, load_city_config, validate_config_dict  # noqa: E402
from core.coverage import measure_city_coverage  # noqa: E402
from core.paths import resolve_pbf_path  # noqa: E402

CKAN_CHECK_TIMEOUT_SECONDS = 15

# bbox'taki yolların en az bu payı demografisi eşlenmiş bir mahalleye düşmeli
# (aşağıya bkz. _coverage_errors); komşu ilçelerin mahalleleri bbox'ın
# kenarlarına her zaman biraz taşar, o yüzden %100 beklenmez.
DEFAULT_MIN_COVERAGE = 0.6

# Gerçek çağrı yerlerindeki (hvi.py) pozisyonel argüman sayısı - isim değil
# sayı karşılaştırılıyor, çünkü adapter yazarları parametrelere farklı isim
# verebilir (bkz. CONTRIBUTING.md'deki adapter sözleşmesi).
#   adapter.fetch_population_data(config)
#   adapter.build_neighborhood_layer(pbf_path, population_paths, config)
REQUIRED_ADAPTER_PARAM_COUNTS = {
    "fetch_population_data": 1,
    "build_neighborhood_layer": 3,
}


def _signature_param_count_error(fn, fn_name: str, expected: int) -> str | None:
    """`fn`'in pozisyonel parametre sayısının `expected` ile eşleştiğini
    doğrular; eşleşmezse hata metnini, uyuyorsa None döner.

    `*args` kabul eden bir imza her zaman geçerli sayılır - esnek bir
    adapter, gerçek çağrının argüman sayısını doğal olarak kabul eder.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None  # imzası incelenemeyen bir çağrılabilir - sessizce atla

    params = list(sig.parameters.values())
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params):
        return None

    positional = [
        p for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    required = [p for p in positional if p.default is inspect.Parameter.empty]

    if len(required) > expected or len(positional) < expected:
        return (
            f"Adapter fonksiyonu '{fn_name}' {expected} pozisyonel argümanla çağrılıyor "
            f"ama imzası {len(positional)} parametre kabul ediyor "
            f"({len(required)} tanesi zorunlu)"
        )
    return None


def validate(city_id: str) -> list[str]:
    errors: list[str] = []
    config_path = CITIES_DIR / city_id / "config.yaml"

    if not config_path.exists():
        return [f"config.yaml bulunamadı: {config_path}"]

    import yaml
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    errors.extend(validate_config_dict(cfg))
    if errors:
        return errors  # temel şema geçersizse ilerisi anlamsız

    config = load_city_config(city_id)

    # Adapter import edilebiliyor mu ve gerekli iki fonksiyonu uyguluyor mu?
    try:
        from core.city_config import load_population_adapter
        adapter = load_population_adapter(config)
        for fn_name, expected_params in REQUIRED_ADAPTER_PARAM_COUNTS.items():
            if not hasattr(adapter, fn_name):
                errors.append(f"Adapter '{config.population_adapter_path}' içinde '{fn_name}' fonksiyonu yok")
                continue
            sig_error = _signature_param_count_error(getattr(adapter, fn_name), fn_name, expected_params)
            if sig_error:
                errors.append(sig_error)
    except ImportError as e:
        errors.append(f"Adapter modülü import edilemedi ('{config.population_adapter_path}'): {e}")

    # OSM pbf URL'i erişilebilir mi? (indirmeden, sadece HEAD isteğiyle)
    try:
        r = requests.head(config.osm_pbf_url, timeout=CKAN_CHECK_TIMEOUT_SECONDS, allow_redirects=True)
        if r.status_code >= 400:
            errors.append(f"OSM pbf URL'i erişilemez görünüyor (HTTP {r.status_code}): {config.osm_pbf_url}")
    except requests.RequestException as e:
        errors.append(f"OSM pbf URL'ine bağlanılamadı: {config.osm_pbf_url} ({e})")

    # CKAN tabanlı nüfus kaynağı tanımlıysa erişilebilirliğini kontrol et.
    ckan_base = cfg.get("population", {}).get("ckan_base")
    if ckan_base:
        try:
            r = requests.get(f"{ckan_base}/api/3/action/site_read", timeout=CKAN_CHECK_TIMEOUT_SECONDS)
            if r.status_code >= 400:
                errors.append(f"CKAN portalına erişilemedi (HTTP {r.status_code}): {ckan_base}")
        except requests.RequestException as e:
            errors.append(f"CKAN portalına bağlanılamadı: {ckan_base} ({e})")

    return errors


def _coverage_errors(config, pbf_path: Path, min_coverage: float) -> list[str]:
    """Şehrin adapter'ını gerçek OSM özütüne karşı çalıştırıp HVI kapsamını
    kontrol eder (bkz. `core/coverage.py`). CSV bütünlük testlerinin
    yakalayamadığı bbox/ilçe-adı hatalarını (kapsam %0) burada görürsün.
    """
    if not pbf_path.exists():
        return [f"OSM özütü bulunamadı ({pbf_path}); --osm-coverage için önce indir (bkz. config.yaml osm.pbf_url)"]
    result = measure_city_coverage(config, pbf_path)
    if result["coverage"] < min_coverage:
        return [
            f"OSM kapsamı yetersiz: bbox'taki {result['yol']:,} yolun yalnızca %{result['coverage'] * 100:.1f}'i "
            f"demografisi olan bir mahalleye düşüyor (en az %{min_coverage * 100:.0f} bekleniyor; "
            f"bulunan ilçeler: {result['ilce']}). bbox'ı yoğun kentsel çekirdeğe göre yeniden çiz "
            f"ya da ilçe adının OSM'deki yazımını kontrol et."
        ]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="src/cities/<sehir>/config.yaml içindeki şehir kimliği")
    parser.add_argument("--osm-coverage", action="store_true",
                        help="Gerçek OSM özütüyle adapter'ı çalıştırıp HVI kapsamını da kontrol et (özüt indirilmiş olmalı)")
    parser.add_argument("--pbf", type=Path, default=None,
                        help="--osm-coverage için OSM .pbf yolu (varsayılan: data/raw/<sehir>/<sehir>.osm.pbf)")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE,
                        help=f"--osm-coverage için en düşük kabul edilen kapsam, 0-1 (varsayılan {DEFAULT_MIN_COVERAGE})")
    args = parser.parse_args()

    errors = validate(args.city)
    if not errors and args.osm_coverage:
        errors = _coverage_errors(load_city_config(args.city), args.pbf or resolve_pbf_path(args.city), args.min_coverage)
    if errors:
        print(f"'{args.city}' doğrulaması BAŞARISIZ:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"'{args.city}' doğrulaması geçti - config.yaml ve adapter kullanıma hazır görünüyor.")


if __name__ == "__main__":
    main()
