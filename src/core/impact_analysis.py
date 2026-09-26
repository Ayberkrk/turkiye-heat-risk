"""Çok yıllı, hava-düzeltilmiş ve müdahale senaryolu ısı riski analizi.

Bu modül ana HVI haritasını değiştirmez. Mevcut yol/raster çıktılarından
ayrı bir, varsayımları görünür analiz paketi üretir: ERA5-Land hava
anomalisi, tampon/ağırlık duyarlılığı, yaş verisiyle yakınsaklık kontrolü
ve varsayımsal ağaçlandırma/gölgeleme senaryoları.
"""

from __future__ import annotations

import json
import hashlib
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterstats
import requests

from core.city_config import CityConfig
from core.hvi import COMPONENT_FLOOR
from core.paths import city_data_proc, city_data_raw, year_paths

WEATHER_API = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_BASELINE = (1991, 2020)
WEATHER_GRID = (4, 3)  # ERA5-Land hücre ölçeğine yakın, şehir içi kaba örnekleme.
WEATHER_TIMEOUT_SECONDS = 120
WEIGHT_PROFILES = {
    "equal": {},
    "heat_priority": {
        "hazard_norm": 2.0, "exposure_norm": 1.2,
        "sensitivity_agac_norm": 1.0, "sensitivity_yasli_norm": 0.8,
        "sensitivity_cocuk_norm": 0.8, "sensitivity_saglik_norm": 0.6,
        "sensitivity_yesil_norm": 0.6, "sensitivity_yapilasma_norm": 0.6,
        "sensitivity_sosyoekonomik_norm": 0.6,
    },
    "equity_priority": {
        "hazard_norm": 1.0, "exposure_norm": 1.2,
        "sensitivity_agac_norm": 1.0, "sensitivity_yasli_norm": 2.0,
        "sensitivity_cocuk_norm": 1.5, "sensitivity_saglik_norm": 1.0,
        "sensitivity_yesil_norm": 0.8, "sensitivity_yapilasma_norm": 0.7,
        "sensitivity_sosyoekonomik_norm": 1.3,
    },
}
def _scene_dates(city_id: str, year: str, main_year: str) -> list[str]:
    raw_dir, _ = year_paths(city_id, year, main_year)
    metadata_path = raw_dir / "scene_metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"{metadata_path} bulunamadı. Önce `pipeline.py --city {city_id} "
            f"--years {' '.join([year])} --main-year {main_year}` çalıştırın."
        )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    return sorted({scene["date"][:10] for scene in payload.get("scenes", []) if scene.get("date")})


def _weather_grid(config: CityConfig) -> list[tuple[float, float]]:
    west, south, east, north = config.bbox
    columns, rows = WEATHER_GRID
    coordinates = {
        (round(float(lat), 5), round(float(lon), 5))
        for lat in np.linspace(south + (north - south) / (2 * rows), north - (north - south) / (2 * rows), rows)
        for lon in np.linspace(west + (east - west) / (2 * columns), east - (east - west) / (2 * columns), columns)
    }
    return sorted(coordinates)


def _load_weather(config: CityConfig, years: list[str]) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
    grid = _weather_grid(config)
    first_year, last_year = min(map(int, years)), max(map(int, years))
    # Landsat sahneleri temmuz/ağustosa düşer; bir haftalık pay, sezon
    # sınırındaki tarihler için de aynı takvim gününün 1991-2020 normalini
    # hesaplanabilir kılar.
    start_date = "1991-06-24"
    end_date = f"{last_year}-09-07"
    cache_dir = city_data_raw(config.city_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    grid_key = hashlib.sha256(repr(grid).encode("utf-8")).hexdigest()[:10]
    cache_path = cache_dir / f"era5land_daily_{first_year}_{last_year}_{grid_key}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return (payload if isinstance(payload, list) else [payload]), grid

    params = {
        "latitude": ",".join(f"{lat:.5f}" for lat, _ in grid),
        "longitude": ",".join(f"{lon:.5f}" for _, lon in grid),
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean",
        "timezone": "Europe/Istanbul",
        "models": "era5_land",
        "temperature_unit": "celsius",
    }
    response = requests.get(WEATHER_API, params=params, timeout=WEATHER_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    locations = payload if isinstance(payload, list) else [payload]
    if len(locations) != len(grid):
        raise ValueError(
            f"ERA5-Land {len(grid)} konum istedi, {len(locations)} sonuç döndürdü."
        )
    cache_path.write_text(json.dumps(locations, ensure_ascii=False), encoding="utf-8")
    return locations, grid


def _temperature_anomalies(
    config: CityConfig, years: list[str], main_year: str,
) -> tuple[dict[str, np.ndarray], list[tuple[float, float]], pd.DataFrame]:
    locations, grid = _load_weather(config, years)
    by_year: dict[str, np.ndarray] = {}
    rows: list[dict[str, Any]] = []
    baseline_start, baseline_end = CLIMATE_BASELINE

    for year in years:
        dates = _scene_dates(config.city_id, year, main_year)
        if not dates:
            raise ValueError(f"{year} için scene_metadata.json içinde sahne tarihi yok.")
        wanted = [date.fromisoformat(day) for day in dates]
        normal_days = {
            day + timedelta(days=offset)
            for day in wanted for offset in range(-7, 8)
        }
        year_anomalies = []
        for grid_id, location in enumerate(locations):
            daily = location.get("daily", {})
            temperatures = dict(zip(daily.get("time", []), daily.get("temperature_2m_mean", [])))
            observed = [float(temperatures[day.isoformat()]) for day in wanted
                        if temperatures.get(day.isoformat()) is not None]
            normals = [float(value) for day_text, value in temperatures.items()
                       if value is not None
                       and baseline_start <= int(day_text[:4]) <= baseline_end
                       and date.fromisoformat(day_text).replace(year=2000) in {
                           d.replace(year=2000) for d in normal_days
                       }]
            if not observed or not normals:
                year_anomalies.append(float("nan"))
                continue
            observed_mean = float(np.mean(observed))
            normal_mean = float(np.mean(normals))
            anomaly = observed_mean - normal_mean
            year_anomalies.append(anomaly)
            rows.append({
                "year": int(year), "grid_id": grid_id,
                "latitude": grid[grid_id][0], "longitude": grid[grid_id][1],
                "scene_dates": ",".join(dates), "scene_date_count": len(dates),
                "era5_scene_day_temp_c": round(observed_mean, 3),
                "era5_1991_2020_normal_c": round(normal_mean, 3),
                "air_temperature_anomaly_c": round(anomaly, 3),
            })
        by_year[year] = np.asarray(year_anomalies, dtype=float)
    return by_year, grid, pd.DataFrame(rows)


def _nearest_grid_for_roads(
    roads: gpd.GeoDataFrame, grid: list[tuple[float, float]], projected_crs: str,
) -> np.ndarray:
    centroids = roads.to_crs(projected_crs).geometry.centroid.to_crs("EPSG:4326")
    xy = np.column_stack((centroids.x.to_numpy(), centroids.y.to_numpy()))
    grid_xy = np.asarray([(lon, lat) for lat, lon in grid])
    # Tek bir şehrin kısa kapsamında en yakın komşu ataması için
    # equirectangular mesafe yeterli ve ek bağımlılık gerektirmiyor.
    scale = math.cos(math.radians(float(np.nanmean(xy[:, 1]))))
    road_x = xy[:, 0] * scale
    point_x = grid_xy[:, 0] * scale
    distances = (road_x[:, None] - point_x[None, :]) ** 2 + (
        xy[:, 1, None] - grid_xy[None, :, 1]
    ) ** 2
    return np.argmin(distances, axis=1)


def _spearman(first: pd.Series, second: pd.Series) -> float:
    """Spearman sıra korelasyonu. `Series.corr(method="spearman")` scipy ister,
    scipy ise requirements.txt'te yok; sıralar üzerinden Pearson aynı sonucu
    (eşitlikte ortalama sıra) ek bağımlılık olmadan verir."""
    return first.rank().corr(second.rank())


def _normalize(values: pd.Series, low: float | None = None, high: float | None = None) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    minimum = float(series.min()) if low is None else low
    maximum = float(series.max()) if high is None else high
    if not np.isfinite(minimum) or not np.isfinite(maximum) or maximum == minimum:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    return ((series - minimum) / (maximum - minimum)).clip(0, 1)


def _active_components(roads: gpd.GeoDataFrame) -> list[str]:
    static = [
        "exposure_norm", "sensitivity_yasli_norm", "sensitivity_cocuk_norm",
        "sensitivity_saglik_norm", "sensitivity_yesil_norm", "sensitivity_yapilasma_norm",
        "sensitivity_sosyoekonomik_norm",
    ]
    return ["hazard_norm", "sensitivity_agac_norm"] + [
        column for column in static if column in roads.columns
    ]


def _weights(profile: str, components: list[str]) -> np.ndarray:
    custom = WEIGHT_PROFILES[profile]
    values = np.asarray([custom.get(column, 1.0) for column in components], dtype=float)
    return values / values.sum()


def _scores_for_buffer(
    roads: gpd.GeoDataFrame,
    years: list[str],
    lst_by_year: dict[str, pd.Series],
    ndvi_by_year: dict[str, pd.Series],
    profile: str,
    lst_bounds: tuple[float, float] | None = None,
) -> dict[str, pd.Series]:
    all_lst = pd.concat([lst_by_year[year] for year in years], ignore_index=True)
    all_ndvi = pd.concat([ndvi_by_year[year] for year in years], ignore_index=True)
    lst_low, lst_high = lst_bounds or (float(all_lst.min()), float(all_lst.max()))
    ndvi_low, ndvi_high = float(all_ndvi.min()), float(all_ndvi.max())
    components = _active_components(roads)
    weights = _weights(profile, components)
    result = {}
    for year in years:
        values = pd.DataFrame(index=roads.index)
        values["hazard_norm"] = _normalize(lst_by_year[year], lst_low, lst_high)
        values["sensitivity_agac_norm"] = 1 - _normalize(ndvi_by_year[year], ndvi_low, ndvi_high)
        for column in components[2:]:
            values[column] = pd.to_numeric(roads[column], errors="coerce")
        complete = values[components].notna().all(axis=1)
        matrix = COMPONENT_FLOOR + (1 - COMPONENT_FLOOR) * values.loc[complete, components]
        result[year] = pd.Series(np.nan, index=roads.index, dtype=float)
        result[year].loc[complete] = np.exp(np.log(matrix).to_numpy() @ weights) * 100
    return result


def _summarize_robustness(
    roads: gpd.GeoDataFrame, years: list[str], scores: dict[str, pd.Series],
    profile: str, buffer_m: int, baseline: dict[str, pd.Series],
) -> dict[str, Any]:
    reference_year = years[-1]
    reference, comparison = baseline[reference_year], scores[reference_year]
    valid = reference.notna() & comparison.notna()
    if not valid.any():
        return {"weight_profile": profile, "buffer_m": buffer_m, "valid_road_count": 0}
    top_n = max(1, int(math.ceil(valid.sum() * 0.10)))
    reference_top = set(reference.loc[valid].nlargest(top_n).index)
    scenario_top = set(comparison.loc[valid].nlargest(top_n).index)
    rank_corr = _spearman(reference.loc[valid], comparison.loc[valid])
    return {
        "weight_profile": profile,
        "buffer_m": buffer_m,
        "reference_year": int(reference_year),
        "valid_road_count": int(valid.sum()),
        "spearman_rank_correlation": round(float(rank_corr), 4) if pd.notna(rank_corr) else None,
        "top_decile_overlap_pct": round(100 * len(reference_top & scenario_top) / top_n, 2),
    }


def _buffer_means(
    roads: gpd.GeoDataFrame, config: CityConfig, years: list[str], main_year: str,
    buffers_m: list[int],
) -> tuple[dict[int, dict[str, pd.Series]], dict[int, dict[str, pd.Series]]]:
    projected = roads.to_crs(config.crs)
    lst: dict[int, dict[str, pd.Series]] = {}
    ndvi: dict[int, dict[str, pd.Series]] = {}
    for buffer_m in buffers_m:
        buffered = gpd.GeoDataFrame(
            geometry=projected.geometry.buffer(buffer_m), crs=config.crs,
        )
        lst[buffer_m], ndvi[buffer_m] = {}, {}
        for year in years:
            _, proc_dir = year_paths(config.city_id, year, main_year)
            lst_path, ndvi_path = proc_dir / "lst_celsius.tif", proc_dir / "ndvi.tif"
            if not lst_path.exists() or not ndvi_path.exists():
                raise FileNotFoundError(
                    f"{year} rasterları bulunamadı. Önce çok yıllı pipeline'ı çalıştırın: {lst_path}"
                )
            with rasterio.open(lst_path) as raster:
                projected_buffers = buffered.to_crs(raster.crs)
            geometries = projected_buffers.geometry
            lst_values = rasterstats.zonal_stats(
                geometries, str(lst_path), stats=["mean"], nodata=-9999.0, all_touched=False,
            )
            ndvi_values = rasterstats.zonal_stats(
                geometries, str(ndvi_path), stats=["mean"], nodata=-9999.0, all_touched=False,
            )
            lst[buffer_m][year] = pd.Series([item["mean"] for item in lst_values], index=roads.index, dtype=float)
            ndvi[buffer_m][year] = pd.Series([item["mean"] for item in ndvi_values], index=roads.index, dtype=float)
            del geometries, projected_buffers
    return lst, ndvi


def _health_convergence(
    roads: gpd.GeoDataFrame, years: list[str], output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if "ilce_adi" not in roads or "yasli_oran" not in roads:
        return pd.DataFrame(), {
            "available": False,
            "reason": "İlçe yaşı ile bağımsız ısı katmanını eşleştirmek için pipeline çıktısında ilce_adi ve yasli_oran gerekli; pipeline yeniden çalıştırılmalı.",
        }
    usable = roads.dropna(subset=["ilce_adi", "yasli_oran"]).copy()
    usable["length"] = pd.to_numeric(usable.get("length", 1), errors="coerce").fillna(1).clip(lower=0.001)
    table = []
    correlations = []
    for district, part in usable.groupby("ilce_adi"):
        row: dict[str, Any] = {
            "district": district,
            "elderly_share": float(np.average(part["yasli_oran"], weights=part["length"])),
            "road_count": int(len(part)),
        }
        for year in years:
            col = f"lst_mean_{year}"
            if col not in part:
                continue
            row[f"mean_lst_{year}_c"] = float(np.average(part[col], weights=part["length"]))
        table.append(row)
    result = pd.DataFrame(table).sort_values("district")
    for year in years:
        temp_col = f"mean_lst_{year}_c"
        valid = result[["elderly_share", temp_col]].dropna() if temp_col in result else pd.DataFrame()
        correlations.append({
            "year": int(year),
            "district_count": int(len(valid)),
            "pearson_r": round(float(valid["elderly_share"].corr(valid[temp_col])), 4)
            if len(valid) >= 3 else None,
            "spearman_rho": round(float(_spearman(valid["elderly_share"], valid[temp_col])), 4)
            if len(valid) >= 3 else None,
            "indicator": "İlçe 65+ yaş nüfus oranı",
            "interpretation": "Yakınsaklık kontrolü; 65+ oranı HVI içinde de bulunduğundan bağımsız doğruluk ölçümü değildir.",
        })
    result.to_csv(output_dir / "heat_health_convergence.csv", index=False)
    return result, {"available": True, "unit": "district", "correlations": correlations,
                    "caveat": "İlçe düzeyindeki yaş oranı HVI bileşenidir; bu karşılaştırma ısı-only LST ile eşleşmeyi gösterir, bağımsız doğruluk kanıtı değildir."}


def _write_map(
    output_path: Path, city_name: str, years: list[str], reference_year: str,
    target_share: float, cooling_c: float, ndvi_delta: float, weather_beta: float,
    map_center: list[float],
) -> None:
    year_options = "".join(f'<option value="{year}">{year}</option>' for year in years)
    template = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__CITY__ çok yıllı ısı ve müdahale senaryoları</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html,body,#map{height:100%;margin:0;font:14px Arial,sans-serif}.panel{position:absolute;z-index:1000;top:12px;left:55px;background:#fff;padding:12px 14px;border-radius:8px;box-shadow:0 1px 8px #5557;max-width:310px}.panel h1{font-size:16px;margin:0 0 8px}.panel label{display:block;margin-top:8px;font-size:12px}select{width:100%;padding:6px}.legend{line-height:19px;margin-top:8px;font-size:12px}.note{color:#555;font-size:11px;line-height:1.35;margin-top:8px}
</style></head><body><div id="map"></div><section class="panel"><h1>__CITY__ | Isı riski ve müdahale senaryoları</h1>
<label>Yıl<select id="year">__YEAR_OPTIONS__</select></label>
<label>Harita katmanı<select id="view"><option value="base">Mevcut HVI</option><option value="weather">Hava-düzeltilmiş HVI (β=__BETA__)</option><option value="trees">Ağaçlandırma senaryosu</option><option value="shade">Gölgeleme senaryosu</option><option value="combined">Birleşik senaryo</option></select></label>
<div id="legend" class="legend"></div>
<div class="note">Hava düzeltmesi ERA5-Land hava sıcaklığı anomalisini LST'den β=__BETA__ varsayımıyla çıkarır. Senaryolar son yıl (__REFERENCE_YEAR__) için en riskli yol segmentlerinin %__TARGET_SHARE__ bölümüne uygulanır: gölgeleme -__COOLING__°C, ağaç örtüsü NDVI +__NDVI__. Bunlar ölçülmüş etki tahmini değildir.</div>
<div class="note">Yol seçerek mahalle/ilçe, 65+ oranı, nüfus yoğunluğu ve skor farkını görün. Bu dosya yanındaki impact_scenarios.geojson ile birlikte yerel bir web sunucusunda açılmalıdır.</div></section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const years=__YEARS__, referenceYear=__REFERENCE_YEAR_JSON__;
const map=L.map('map').setView(__CENTER__,11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
let layer;let features=[];
function metric(feature){const p=feature.properties,y=document.getElementById('year').value,v=document.getElementById('view').value;
 if(v==='weather')return p['hvi_weather_'+y];if(v==='trees')return y===referenceYear?p.hvi_trees:null;
 if(v==='shade')return y===referenceYear?p.hvi_shade:null;if(v==='combined')return y===referenceYear?p.hvi_combined:null;return p['hvi_base_'+y];}
function color(value,breaks){if(value===null||value===undefined||!Number.isFinite(Number(value)))return '#aaa';let i=breaks.findIndex(b=>Number(value)<=b);return ['#3182bd','#74add1','#fed976','#fd8d3c','#a50026'][i<0?4:i];}
function draw(){if(layer)map.removeLayer(layer);const vals=features.map(f=>metric(f)).filter(v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))).map(Number).sort((a,b)=>a-b);
 if(!vals.length){document.getElementById('legend').textContent='Müdahale senaryoları yalnızca son analiz yılı için gösterilir.';return;}
 const breaks=[.2,.4,.6,.8].map(q=>vals[Math.min(vals.length-1,Math.floor(q*(vals.length-1)))]).concat([Infinity]);
 layer=L.geoJSON(features,{style:f=>({color:color(metric(f),breaks),weight:2,opacity:.82}),onEachFeature:(f,l)=>{const p=f.properties,y=document.getElementById('year').value,v=metric(f),base=p['hvi_base_'+y];
 l.bindPopup(`<b>${p.name||'Yol segmenti'}</b><br>${p.mahalle_adi||''} · ${p.ilce_adi||''}<br>65+ oranı: ${p.yasli_oran==null?'veri yok':(100*p.yasli_oran).toFixed(1)+'%'}<br>Nüfus yoğunluğu: ${p.nufus_yogunlugu==null?'veri yok':Number(p.nufus_yogunlugu).toFixed(0)+' kişi/km²'}<br>Gösterilen HVI: ${v==null?'uygulanamaz':Number(v).toFixed(1)}<br>Temel HVI: ${base==null?'veri yok':Number(base).toFixed(1)}<br>Fark: ${v==null||base==null?'-':(Number(v)-Number(base)).toFixed(1)}`)}}).addTo(map);
 document.getElementById('legend').innerHTML=`Skorun şehir içindeki sıralaması:<br>${['Düşük','Orta-düşük','Orta-yüksek','Yüksek','En yüksek'].map((n,i)=>`<span style="color:${['#3182bd','#74add1','#fed976','#fd8d3c','#a50026'][i]}">■</span> ${n}`).join('<br>')}`;}
Promise.all([fetch('./impact_scenarios.geojson').then(r=>{if(!r.ok)throw Error('GeoJSON yüklenemedi');return r.json()}),fetch('./analysis_summary.json').then(r=>r.json())]).then(([data,summary])=>{features=data.features;const center=summary.map_center;if(center)map.setView(center,12);draw()}).catch(e=>{document.getElementById('legend').textContent=e.message+' - analiz klasörünü HTTP üzerinden açın.'});
document.getElementById('year').addEventListener('change',draw);document.getElementById('view').addEventListener('change',draw);
</script></body></html>"""
    html = (template.replace("__CITY__", city_name)
            .replace("__YEAR_OPTIONS__", year_options)
            .replace("__REFERENCE_YEAR__", str(reference_year))
            .replace("__REFERENCE_YEAR_JSON__", json.dumps(reference_year))
            .replace("__TARGET_SHARE__", f"{target_share * 100:g}")
            .replace("__COOLING__", f"{cooling_c:g}")
            .replace("__NDVI__", f"{ndvi_delta:g}")
            .replace("__BETA__", f"{weather_beta:g}")
            .replace("__YEARS__", json.dumps(years))
            .replace("__CENTER__", json.dumps(map_center)))
    output_path.write_text(html, encoding="utf-8")

def _make_impact_geodata(
    roads: gpd.GeoDataFrame, years: list[str], base_scores: dict[str, pd.Series],
    weather_scores: dict[str, pd.Series], latest_lst: pd.Series, latest_ndvi: pd.Series,
    component_bounds: dict[str, tuple[float, float]], target_share: float,
    cooling_c: float, ndvi_delta: float,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    output = roads[[column for column in ["geometry", "name", "mahalle_adi", "ilce_adi", "nufus_yogunlugu", "yasli_oran", "cocuk_oran", "length"] if column in roads]].copy()
    for year in years:
        output[f"hvi_base_{year}"] = base_scores[year]
        output[f"hvi_weather_{year}"] = weather_scores[year]
    reference_year = years[-1]
    base = base_scores[reference_year]
    valid = base.notna()
    target_count = max(1, int(math.ceil(int(valid.sum()) * target_share)))
    target_index = set(base.loc[valid].nlargest(target_count).index)
    mask = pd.Series(output.index.isin(target_index), index=output.index)

    def score(lst: pd.Series, ndvi: pd.Series) -> pd.Series:
        components = _active_components(roads)
        values = pd.DataFrame(index=roads.index)
        values["hazard_norm"] = _normalize(lst, *component_bounds["lst"])
        values["sensitivity_agac_norm"] = 1 - _normalize(ndvi, *component_bounds["ndvi"])
        for column in components[2:]:
            values[column] = pd.to_numeric(roads[column], errors="coerce")
        valid_rows = values[components].notna().all(axis=1)
        result = pd.Series(np.nan, index=roads.index, dtype=float)
        matrix = COMPONENT_FLOOR + (1 - COMPONENT_FLOOR) * values.loc[valid_rows, components]
        result.loc[valid_rows] = np.exp(np.log(matrix).mean(axis=1).to_numpy()) * 100
        return result

    ndvi_low, ndvi_high = component_bounds["ndvi"]
    tree_ndvi = latest_ndvi.copy()
    shade_lst = latest_lst.copy()
    tree_ndvi.loc[mask] = (tree_ndvi.loc[mask] + ndvi_delta).clip(ndvi_low, ndvi_high)
    shade_lst.loc[mask] = shade_lst.loc[mask] - cooling_c
    combined_ndvi, combined_lst = tree_ndvi.copy(), shade_lst.copy()
    scores = {
        "base": base,
        "trees": score(latest_lst, tree_ndvi),
        "shade": score(latest_lst.where(~mask, shade_lst), latest_ndvi),
        "combined": score(combined_lst, combined_ndvi),
    }
    for key in ("trees", "shade", "combined"):
        output[f"hvi_{key}"] = scores[key]
    output["targeted_for_scenario"] = mask.astype(int)
    output = output.to_crs("EPSG:4326")

    rows = []
    if "yasli_oran" in output:
        older = pd.to_numeric(output["yasli_oran"], errors="coerce")
        elderly_cut = older.quantile(0.8)
        for name, values in scores.items():
            delta = values - base
            rows.append({
                "scenario": name,
                "reference_year": int(reference_year),
                "target_share": target_share if name != "base" else 0.0,
                "targeted_road_count": int(mask.sum()) if name != "base" else 0,
                "targeted_roads_in_top_elderly_quintile_pct": round(
                    100 * float((mask & (older >= elderly_cut)).sum()) / max(int(mask.sum()), 1), 2,
                ) if name != "base" else 0.0,
                "mean_elderly_share_target_pct": round(100 * float(older[mask].mean()), 2) if name != "base" and older[mask].notna().any() else None,
                "mean_population_density_target": round(float(pd.to_numeric(output.loc[mask, "nufus_yogunlugu"], errors="coerce").mean()), 2)
                if name != "base" and "nufus_yogunlugu" in output else None,
                "mean_hvi_delta_target": round(float(delta[mask].mean()), 3) if name != "base" else 0.0,
                "mean_hvi_delta_all_roads": round(float(delta.mean()), 3) if name != "base" else 0.0,
                "assumption": "NDVI artışı" if name == "trees" else "LST düşüşü" if name == "shade" else "NDVI artışı ve LST düşüşü" if name == "combined" else "Observed inputs",
            })
    return output, pd.DataFrame(rows)


def run_impact_analysis(
    config: CityConfig,
    years: list[str],
    main_year: str,
    buffers_m: list[int] | None = None,
    cooling_c: float = 2.0,
    ndvi_delta: float = 0.15,
    target_share: float = 0.20,
    weather_beta: float = 1.0,
    refresh_weather: bool = False,
) -> Path:
    """Tamamlanmış çok yıllı bir şehir pipeline'ını analiz edip yanındaki raporu yazar."""
    years = [str(year) for year in years]
    if len(set(years)) < 3:
        raise ValueError("Çok yıllı trend için en az üç farklı yıl gerekli.")
    if not 0 < target_share <= 1:
        raise ValueError("target_share 0'dan büyük ve 1'den küçük/eşit olmalı.")
    if cooling_c < 0 or ndvi_delta < 0:
        raise ValueError("Senaryo etkileri negatif olmayan büyüklükler olmalı.")
    if weather_beta < 0:
        raise ValueError("weather_beta negatif olamaz.")
    buffers = sorted(set(buffers_m or [config.buffer_meters, 30, 50]))
    if any(buffer_m <= 0 for buffer_m in buffers):
        raise ValueError("Tampon genişlikleri pozitif metre değeri olmalı.")
    if config.buffer_meters not in buffers:
        buffers.insert(0, config.buffer_meters)
    years = sorted(set(years), key=int)

    proc_dir = city_data_proc(config.city_id)
    roads_path = proc_dir / "roads_with_hvi.geojson"
    if not roads_path.exists():
        raise FileNotFoundError(f"{roads_path} bulunamadı. Önce `pipeline.py` çalıştırın.")
    roads = gpd.read_file(roads_path)
    for year in years:
        for prefix in ("lst_mean", "ndvi_mean"):
            if f"{prefix}_{year}" not in roads:
                raise ValueError(f"{roads_path.name} içinde {prefix}_{year} yok; belirtilen yıllarla pipeline'ı çalıştırın.")

    output_dir = proc_dir / "impact_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    # İndirilen ERA5-Land yanıtı önbellekte tutulur; yeniden çalıştırmalar
    # aynı veriyle tekrar üretilebilir olsun diye tekrar indirilmez.
    if refresh_weather:
        for cached in city_data_raw(config.city_id).glob("era5land_daily_*.json"):
            cached.unlink()
    anomalies, grid, weather_detail = _temperature_anomalies(config, years, main_year)
    weather_detail.to_csv(output_dir / "weather_grid.csv", index=False)
    nearest = _nearest_grid_for_roads(roads, grid, config.crs)
    weather_anomaly_by_year = {year: values[nearest] for year, values in anomalies.items()}

    raw_lst = {year: pd.to_numeric(roads[f"lst_mean_{year}"], errors="coerce") for year in years}
    raw_ndvi = {year: pd.to_numeric(roads[f"ndvi_mean_{year}"], errors="coerce") for year in years}
    weather_lst = {
        year: raw_lst[year] - weather_beta * pd.Series(weather_anomaly_by_year[year], index=roads.index)
        for year in years
    }
    annual = []
    for year in years:
        valid = raw_lst[year].notna() & weather_lst[year].notna()
        if not valid.any():
            continue
        mean_weather_anomaly = float(np.nanmean(anomalies[year]))
        annual.append({
            "year": int(year),
            "scene_dates": ",".join(_scene_dates(config.city_id, year, main_year)),
            "scene_count": len(_scene_dates(config.city_id, year, main_year)),
            "valid_road_count": int(valid.sum()),
            "mean_lst_c": round(float(raw_lst[year][valid].mean()), 3),
            "median_lst_c": round(float(raw_lst[year][valid].median()), 3),
            "mean_era5_air_temp_anomaly_c": round(mean_weather_anomaly, 3),
            "mean_weather_adjusted_lst_c": round(float(weather_lst[year][valid].mean()), 3),
            "weather_beta": weather_beta,
            "beta_0_mean_lst_c": round(float(raw_lst[year][valid].mean()), 3),
            "beta_0_5_mean_lst_c": round(float((raw_lst[year][valid] - 0.5 * pd.Series(weather_anomaly_by_year[year], index=roads.index)[valid]).mean()), 3),
            "beta_1_mean_lst_c": round(float((raw_lst[year][valid] - pd.Series(weather_anomaly_by_year[year], index=roads.index)[valid]).mean()), 3),
        })
    annual_df = pd.DataFrame(annual)
    annual_df.to_csv(output_dir / "annual_weather_adjusted.csv", index=False)
    if len(annual_df) >= 2:
        trend_raw = float(np.polyfit(annual_df["year"], annual_df["mean_lst_c"], 1)[0])
        trend_adjusted = float(np.polyfit(annual_df["year"], annual_df["mean_weather_adjusted_lst_c"], 1)[0])
    else:
        trend_raw = trend_adjusted = float("nan")

    lst_buffers, ndvi_buffers = _buffer_means(roads, config, years, main_year, buffers)
    robustness_rows = []
    default_buffer = config.buffer_meters
    baseline = _scores_for_buffer(roads, years, lst_buffers[default_buffer], ndvi_buffers[default_buffer], "equal")
    for buffer_m in buffers:
        for profile in WEIGHT_PROFILES:
            scores = _scores_for_buffer(roads, years, lst_buffers[buffer_m], ndvi_buffers[buffer_m], profile)
            robustness_rows.append(_summarize_robustness(
                roads, years, scores, profile, buffer_m, baseline,
            ))
    robustness = pd.DataFrame(robustness_rows)
    robustness.to_csv(output_dir / "robustness.csv", index=False)

    # Harita skorları tüm yıllar için tek ortak bileşen ölçeği kullanır. HVI,
    # ana ürünle aynı eşit ağırlıklı geometrik ortalamayla yeniden hesaplanır.
    all_base_lst = pd.concat(list(lst_buffers[default_buffer].values()), ignore_index=True)
    all_base_ndvi = pd.concat(list(ndvi_buffers[default_buffer].values()), ignore_index=True)
    bounds = {
        "lst": (float(all_base_lst.min()), float(all_base_lst.max())),
        "ndvi": (float(all_base_ndvi.min()), float(all_base_ndvi.max())),
    }
    base_scores = _scores_for_buffer(roads, years, lst_buffers[default_buffer], ndvi_buffers[default_buffer], "equal")
    adjusted_by_year = {}
    for year in years:
        corrected = raw_lst[year] - weather_beta * pd.Series(weather_anomaly_by_year[year], index=roads.index)
        adjusted_by_year[year] = corrected
    weather_scores = _scores_for_buffer(
        roads, years, adjusted_by_year, ndvi_buffers[default_buffer], "equal",
        lst_bounds=bounds["lst"],
    )
    center = [float((config.bbox[1] + config.bbox[3]) / 2), float((config.bbox[0] + config.bbox[2]) / 2)]
    impact, interventions = _make_impact_geodata(
        roads, years, base_scores, weather_scores, raw_lst[years[-1]], raw_ndvi[years[-1]],
        bounds, target_share, cooling_c, ndvi_delta,
    )
    if not interventions.empty:
        interventions.to_csv(output_dir / "intervention_scenarios.csv", index=False)
    impact.to_file(output_dir / "impact_scenarios.geojson", driver="GeoJSON")

    _, health_summary = _health_convergence(roads, years, output_dir)
    summary = {
        "city_id": config.city_id,
        "city_name": config.name,
        "years": [int(year) for year in years],
        "reference_year": int(years[-1]),
        "road_count": int(len(roads)),
        "map_center": center,
        "weather_source": "Open-Meteo Historical Weather API, ERA5-Land, daily 2 m mean air temperature",
        "weather_source_url": WEATHER_API,
        "weather_climatology_period": f"{CLIMATE_BASELINE[0]}-{CLIMATE_BASELINE[1]}",
        "weather_beta": weather_beta,
        "raw_lst_linear_trend_c_per_year": round(trend_raw, 5) if np.isfinite(trend_raw) else None,
        "weather_adjusted_lst_linear_trend_c_per_year": round(trend_adjusted, 5) if np.isfinite(trend_adjusted) else None,
        "weather_method_caveat": "ERA5-Land hava sıcaklığı anomalisi, seçilen Landsat sahne günlerinin 1991-2020 aynı-takvim-penceresi normalinden çıkarılır. β varsayımdır; β=0/0.5/1 duyarlılığı annual_weather_adjusted.csv içinde verilir. 2 m hava sıcaklığı ile uydu yüzey sıcaklığı aynı ölçüm değildir; düzeltilmiş değer ikinci bir tahmin olarak yorumlanmalıdır.",
        "buffers_m": buffers,
        "weight_profiles": {
            profile: {
                component: float(weight)
                for component, weight in zip(
                    _active_components(roads), _weights(profile, _active_components(roads)),
                )
            }
            for profile in WEIGHT_PROFILES
        },
        "robustness_baseline": {"buffer_m": default_buffer, "weight_profile": "equal"},
        "validation": health_summary,
        "intervention_assumptions": {
            "target_share": target_share,
            "targeting_rule": f"Son yıl eşit ağırlıklı HVI sıralamasındaki üst %{target_share * 100:g} yol segmenti",
            "cooling_c": cooling_c,
            "ndvi_increase": ndvi_delta,
            "caveat": "Senaryolar doğrusal endeks what-if hesaplarıdır; ağaç/gölge etkisi ölçülmüş değildir, yayılım/uygulama maliyeti/termal konfor veya sağlık sonucu modellenmez.",
        },
        "annual": annual,
        "outputs": [
            "annual_weather_adjusted.csv", "weather_grid.csv", "robustness.csv",
            "heat_health_convergence.csv", "intervention_scenarios.csv",
            "impact_scenarios.geojson", "analysis_map.html",
        ],
    }
    (output_dir / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_map(
        output_dir / "analysis_map.html", config.name, years, years[-1],
        target_share, cooling_c, ndvi_delta, weather_beta, center,
    )
    print(f"Analiz paketi kaydedildi: {output_dir}")
    return output_dir
