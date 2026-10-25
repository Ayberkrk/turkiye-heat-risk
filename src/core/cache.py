"""Ara çıktı dosyaları için basit sürüm damgalı önbellek geçerliliği.

`roads_timeseries.geojson` ve `roads_with_hvi.geojson` üretimi pahalıdır
(uydu mozaikleri, OSM sorguları, mekansal join'ler); bu yüzden dosya zaten
varsa yeniden hesaplanmaz. Ama formül değiştiğinde (ör. `hvi.py`'deki
bileşen sayısı veya birleştirme yöntemi) eski dosya sessizce güncel gibi
kullanılırdı - bunu önlemek için her üretici modül kendi sürüm numarasını
küçük bir `.meta.json` yan dosyasına yazar; sürüm uyuşmazsa önbellek
geçersiz sayılır.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _meta_path(output_path: Path) -> Path:
    return output_path.with_name(output_path.name + ".meta.json")


@contextmanager
def atomic_output_path(output_path: Path) -> Iterator[Path]:
    """Yield a sibling temporary path and publish it only after a full write.

    Keeping the temporary file beside its destination makes ``replace`` an
    atomic rename on the same filesystem. The final extension is preserved so
    geospatial writers can still infer the output driver from the filename.
    """
    output_path = Path(output_path)
    temporary = output_path.with_name(f"{output_path.stem}.part{output_path.suffix}")
    try:
        yield temporary
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def fingerprint_digest(fingerprint: Any) -> str:
    """Return a stable digest for JSON-compatible cache inputs.

    A digest keeps sidecar metadata small while making changes to the declared
    inputs invalidate an otherwise version-compatible result. Callers should
    pass only stable values (paths/stat signatures/config), never signed URLs
    or other ephemeral values.
    """
    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_signature(path: Path) -> dict[str, Any]:
    """Describe a local input without reading large rasters/PBFs into memory."""
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path), "exists": True, "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def is_cache_valid(output_path: Path, version: int, force: bool = False,
                   fingerprint: Any | None = None) -> bool:
    """Çıktı dosyası, verilen sürüm için hâlâ geçerli mi?

    `force=True` ise (CLI'dan --force ile) her zaman False döner - dosya
    zaten güncel olsa bile yeniden hesaplama zorlanır.
    """
    if force:
        return False
    if not output_path.exists():
        return False
    meta_path = _meta_path(output_path)
    if not meta_path.exists():
        # Bu mekanizmadan önce üretilmiş eski bir dosya olabilir - güvenli
        # taraf, geçersiz saymak ve yeniden hesaplamaktır.
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if meta.get("version") != version:
        return False
    if fingerprint is not None:
        return meta.get("fingerprint_sha256") == fingerprint_digest(fingerprint)
    return True


def write_cache_meta(output_path: Path, version: int, fingerprint: Any | None = None,
                     details: dict[str, Any] | None = None) -> None:
    """Write cache metadata atomically, optionally recording input identity.

    `details` stores small run diagnostics such as per-year data coverage.
    Sidecars without an input fingerprint remain readable for callers that
    have not yet adopted input-sensitive invalidation.
    """
    payload: dict[str, Any] = {"version": version}
    if fingerprint is not None:
        payload["fingerprint_sha256"] = fingerprint_digest(fingerprint)
    if details:
        payload["details"] = details
    meta_path = _meta_path(output_path)
    temporary = meta_path.with_name(meta_path.name + ".part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    temporary.replace(meta_path)
