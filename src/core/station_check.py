"""Uydu yüzey sıcaklığının meteoroloji istasyonlarının hava sıcaklığıyla karşılaştırılması.

Bu bir HVI doğrulaması değildir: endeksin sağlık sonuçlarını öngörüp
öngörmediğini söylemez. Daha dar bir soruyu yanıtlar: hattın kullandığı
Landsat yüzey sıcaklığı (LST), aynı anda ölçülen bağımsız bir sıcaklıkla
tutarlı mı? Somut olarak:

  1. Sahne bazında: her Landsat geçişinde, istasyonun bulunduğu 3x3 piksellik
     alandaki (90 m) bulutsuz LST medyanı ile istasyonun geçişe en yakın
     saatlik hava sıcaklığı. LST tipik olarak gündüz hava sıcaklığından
     yüksektir (yüzey güneşle ısınır); beklenen, farkın istasyondan istasyona
     makul ve tutarlı olması ve iki sıcaklığın günden güne birlikte
     değişmesidir.
  2. Yıllar arası: iki yılda da ölçümü olan istasyonlarda, yaz geçişlerinin
     ortalama LST farkı ile aynı anların ortalama hava sıcaklığı farkı. Bu,
     README'deki "2020-2026 yol LST farkı" bulgusunun hava koşullarından ne
     kadar etkilenmiş olabileceğine dair kaba bir kontroldür.

İstasyonlar NOAA'nın Global Historical Climatology Network hourly (GHCNh)
veri setinden, şehir bbox'ı içindekiler otomatik bulunarak alınır (kamu malı,
bkz. https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly).
İstasyon sayısı bir şehirde genelde 1-5'tir; sonuçlar bu yüzden betimleyicidir,
istatistiksel bir doğrulama değil.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import transform as transform_points

from core.cache import atomic_output_path
from core.city_config import CityConfig
from core.paths import city_data_proc, city_data_raw, year_paths
from core.raster import qa_invalid_mask

GHCNH_BASE = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly"
STATION_LIST_URL = f"{GHCNH_BASE}/doc/ghcnh-station-list.csv"
STATION_LIST_COLUMNS = ["id", "lat", "lon", "elevation", "state", "name", "gsn", "hcn", "wmo", "icao", "country"]

# Landsat 8/9 Türkiye üzerinden yaklaşık 08:30-08:50 UTC'de geçer. Saatlik
# kayıtlardan geçiş anına en yakın olan, en fazla bu kadar uzaktaysa kullanılır.
OVERPASS_UTC = "08:40"
MAX_TIME_GAP = timedelta(minutes=45)
# İstasyon pikselinin çevresi: 3x3 piksel (~90 m). Termal bandın gerçek
# çözünürlüğü 100 m olduğu için tek piksel yerine küçük bir alanın medyanı.
WINDOW_RADIUS_PX = 1
MIN_VALID_PIXELS = 5
DOWNLOAD_TIMEOUT_SECONDS = 300


def _cache_dir(config: CityConfig) -> Path:
    path = city_data_raw(config.city_id) / "istasyon"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size > 0:
        return path
    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    response.raise_for_status()
    with atomic_output_path(path) as temporary:
        temporary.write_bytes(response.content)
    return path


def stations_in_bbox(station_list: pd.DataFrame, bbox: list[float]) -> pd.DataFrame:
    west, south, east, north = bbox
    inside = station_list["lat"].between(south, north) & station_list["lon"].between(west, east)
    return station_list[inside].reset_index(drop=True)


def load_station_list(config: CityConfig) -> pd.DataFrame:
    path = _download(STATION_LIST_URL, _cache_dir(config) / "ghcnh-station-list.csv")
    frame = pd.read_csv(path, dtype=str)
    frame.columns = STATION_LIST_COLUMNS[: len(frame.columns)]
    frame[["lat", "lon"]] = frame[["lat", "lon"]].apply(pd.to_numeric, errors="coerce")
    return frame.dropna(subset=["lat", "lon"])


def parse_ghcnh(text: str) -> pd.DataFrame:
    """GHCNh PSV dosyasından zaman (UTC) ve hava sıcaklığı (°C).

    Kalite kodu harf olan kayıtlar (GHCNh'nin başarısız kalite testi
    işaretleri) atılır; rakam ya da boş kodlar kaynak/ölçüm bilgisidir.
    """
    frame = pd.read_csv(io.StringIO(text), sep="|", dtype=str, usecols=lambda c: c in {
        "DATE", "temperature", "temperature_Quality_Code"})
    frame = frame.dropna(subset=["DATE", "temperature"])
    quality = frame["temperature_Quality_Code"].fillna("")
    frame = frame[~quality.str.match(r"^[A-Za-z]")]
    return pd.DataFrame({
        "time": pd.to_datetime(frame["DATE"], utc=True),
        "air_temp_c": pd.to_numeric(frame["temperature"], errors="coerce"),
    }).dropna().sort_values("time").reset_index(drop=True)


def load_station_year(config: CityConfig, station_id: str, year: str) -> pd.DataFrame:
    url = f"{GHCNH_BASE}/access/by-year/{year}/psv/GHCNh_{station_id}_{year}.psv"
    path = _cache_dir(config) / f"GHCNh_{station_id}_{year}.psv"
    try:
        _download(url, path)
    except requests.HTTPError:
        return pd.DataFrame(columns=["time", "air_temp_c"])
    return parse_ghcnh(path.read_text(encoding="utf-8", errors="replace"))


def nearest_observation(observations: pd.DataFrame, when: datetime) -> float | None:
    if observations.empty:
        return None
    when = pd.Timestamp(when)
    gaps = (observations["time"] - when).abs()
    index = gaps.idxmin()
    return float(observations.loc[index, "air_temp_c"]) if gaps.loc[index] <= MAX_TIME_GAP else None


def lst_at_point(thermal_path: Path, qa_path: Path, lon: float, lat: float) -> tuple[float | None, int]:
    """İstasyonun çevresindeki 3x3 pikselde bulutsuz LST medyanı (°C) ve geçerli piksel sayısı."""
    with rasterio.open(thermal_path) as thermal, rasterio.open(qa_path) as qa:
        xs, ys = transform_points("EPSG:4326", thermal.crs, [lon], [lat])
        row, col = thermal.index(xs[0], ys[0])
        r0, c0 = row - WINDOW_RADIUS_PX, col - WINDOW_RADIUS_PX
        size = 2 * WINDOW_RADIUS_PX + 1
        if r0 < 0 or c0 < 0 or r0 + size > thermal.height or c0 + size > thermal.width:
            return None, 0
        window = ((r0, r0 + size), (c0, c0 + size))
        raw = thermal.read(1, window=window).astype("float64")
        invalid = qa_invalid_mask(qa.read(1, window=window))
        if thermal.nodata is not None:
            invalid |= raw == thermal.nodata
    values = (raw * 0.00341802 + 149.0 - 273.15)[~invalid]
    if values.size < MIN_VALID_PIXELS:
        return None, int(values.size)
    return float(np.median(values)), int(values.size)


def compare_scenes(config: CityConfig, years: list[str], main_year: str,
                   stations: pd.DataFrame) -> pd.DataFrame:
    """Her (sahne, istasyon) çifti için LST ve geçiş anındaki hava sıcaklığı."""
    rows = []
    for year in years:
        raw_dir, _ = year_paths(config.city_id, year, main_year)
        metadata = json.loads((raw_dir / "scene_metadata.json").read_text(encoding="utf-8"))
        observations = {sid: load_station_year(config, sid, year) for sid in stations["id"]}
        for scene in metadata.get("scenes", []):
            scene_dir = raw_dir / scene["folder"]
            when = datetime.fromisoformat(f"{scene['date']}T{OVERPASS_UTC}:00+00:00")
            for _, station in stations.iterrows():
                lst, n_valid = lst_at_point(scene_dir / "band10_thermal.tif", scene_dir / "band_qa_pixel.tif",
                                            station["lon"], station["lat"])
                air = nearest_observation(observations[station["id"]], when)
                if lst is None or air is None:
                    continue
                rows.append({
                    "yil": year, "tarih": scene["date"], "sahne": scene["scene_id"],
                    "istasyon": station["id"], "istasyon_adi": station["name"],
                    "lst_c": round(lst, 2), "hava_sicakligi_c": round(air, 1),
                    "fark_c": round(lst - air, 2), "gecerli_piksel": n_valid,
                })
    table = pd.DataFrame(rows)
    # Komşu karolar aynı günü iki kez görebilir; aynı istasyon-gün tek satır olsun.
    if not table.empty:
        table = table.groupby(["yil", "tarih", "istasyon", "istasyon_adi"], as_index=False).agg(
            lst_c=("lst_c", "median"), hava_sicakligi_c=("hava_sicakligi_c", "first"),
            fark_c=("fark_c", "median"), gecerli_piksel=("gecerli_piksel", "max"), sahne=("sahne", "first"),
        )
    return table


def summarize(table: pd.DataFrame, years: list[str]) -> dict:
    if table.empty:
        return {"pairs": 0}
    per_station = table.groupby(["istasyon", "istasyon_adi"]).agg(
        cift=("fark_c", "size"), ort_fark_c=("fark_c", "mean"), sd_fark_c=("fark_c", "std"),
    ).round(2).reset_index()
    # Gün gün birlikte değişim: istasyonun kendi ortalamasından sapmalar
    # (istasyonlar arası sabit farkı ayırmak için).
    anomaly = table.assign(
        lst_a=table["lst_c"] - table.groupby("istasyon")["lst_c"].transform("mean"),
        air_a=table["hava_sicakligi_c"] - table.groupby("istasyon")["hava_sicakligi_c"].transform("mean"),
    )
    temporal_r = float(anomaly["lst_a"].corr(anomaly["air_a"])) if len(anomaly) > 2 else None

    year_change = []
    if len(years) > 1:
        first, last = years[0], years[-1]
        means = table.groupby(["istasyon", "istasyon_adi", "yil"])[["lst_c", "hava_sicakligi_c"]].mean().unstack("yil")
        for (sid, name), row in means.iterrows():
            if pd.notna(row.get(("lst_c", first))) and pd.notna(row.get(("lst_c", last))):
                year_change.append({
                    "istasyon": sid, "istasyon_adi": name,
                    "lst_degisim_c": round(row[("lst_c", last)] - row[("lst_c", first)], 2),
                    "hava_degisim_c": round(row[("hava_sicakligi_c", last)] - row[("hava_sicakligi_c", first)], 2),
                })
    return {
        "pairs": int(len(table)),
        "stations": per_station.to_dict(orient="records"),
        "pearson_all_pairs": round(float(table["lst_c"].corr(table["hava_sicakligi_c"])), 3) if len(table) > 2 else None,
        "pearson_within_station_anomalies": round(temporal_r, 3) if temporal_r is not None else None,
        "year_change": year_change,
    }


def run_station_check(config: CityConfig, years: list[str], main_year: str) -> Path:
    stations = stations_in_bbox(load_station_list(config), config.bbox)
    output_dir = city_data_proc(config.city_id) / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"{config.name}: bbox içinde {len(stations)} GHCNh istasyonu: {', '.join(stations['name'])}")
    table = compare_scenes(config, years, main_year, stations)
    summary = summarize(table, years)
    summary.update({"city_id": config.city_id, "years": years, "overpass_utc": OVERPASS_UTC,
                    "max_time_gap_min": int(MAX_TIME_GAP.total_seconds() // 60),
                    "source": "NOAA GHCNh (kamu malı)"})
    with atomic_output_path(output_dir / "istasyon_karsilastirma.csv") as temporary:
        table.to_csv(temporary, index=False)
    with atomic_output_path(output_dir / "istasyon_ozet.json") as temporary:
        temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not table.empty:
        _plot(table, output_dir / "istasyon_karsilastirma.png", config.name)
    return output_dir


def _plot(table: pd.DataFrame, path: Path, city: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 5.5), dpi=150)
    for (name, year), group in table.groupby(["istasyon_adi", "yil"]):
        ax.scatter(group["hava_sicakligi_c"], group["lst_c"], s=28, label=f"{name} ({year})",
                   marker="o" if year == table["yil"].min() else "^")
    low = min(table["hava_sicakligi_c"].min(), table["lst_c"].min()) - 2
    high = max(table["hava_sicakligi_c"].max(), table["lst_c"].max()) + 2
    ax.plot([low, high], [low, high], color="#999999", lw=1, ls="--", label="LST = hava sıcaklığı")
    ax.set_xlabel("İstasyon hava sıcaklığı, geçiş anı (°C)")
    ax.set_ylabel("Landsat yüzey sıcaklığı, istasyon çevresi 90 m (°C)")
    ax.set_title(f"{city}: uydu yüzey sıcaklığı ve istasyon hava sıcaklığı", loc="left", fontsize=11)
    ax.legend(fontsize=7, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png")
    plt.close(fig)
