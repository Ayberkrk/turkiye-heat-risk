"""Mekânsal tampon duyarlılığı ve 2020-2026 HVI değişiminin bileşenlere ayrıştırılması.

İki analiz de ana HVI'nin kendi adımlarını (core/hvi.py) kullanır; böylece
ölçülen fark yöntem farkı değil, yalnızca değiştirilen girdinin etkisidir.

1. Tampon duyarlılığı. Yol sıcaklığı ve NDVI, yol ekseninin çevresindeki bir
   tamponun ortalamasıdır (varsayılan 10 m). Tampon 30 ya da 50 m olunca hangi
   yolların sırası değişiyor? Geniş bulvarlarda dar tampon koridorun yalnızca
   asfaltını, dar sokaklarda geniş tampon komşu yapı adalarını da örnekler; bu
   yüzden değişimin yol tipine göre dağılımı raporlanır. `core/impact_analysis.py`
   aynı soruyu en az üç yıl ve hava düzeltmesiyle sorar; bu modül iki yıllık
   standart çıktıyla çalışır ve yol düzeyinde sonuç üretir.

2. Zamansal ayrıştırma. Haritadaki 2020 ve 2026 skorları yalnızca yüzey
   sıcaklığı ve NDVI'de farklıdır: nüfus (İzmir'de 2023 TÜİK mahalle verisi,
   TÜİK şablonlu şehirlerde 2025 ilçe sayımı), yaş yapısı, SEGE-2022 ve OSM
   bileşenleri iki yılda da aynı tutulur. Bu, 2020 skorunun 2020 nüfusuyla
   değil sonraki bir yılın nüfusuyla hesaplandığı anlamına gelir ve bu
   modül bunun etkisini ÖLÇEMEZ: açık veride 2020 mahalle nüfusu yok. Ölçtüğü
   şey, değişimin ne kadarının sıcaklıktan ne kadarının bitki örtüsünden
   geldiğidir (iki etkenli Shapley ayrıştırması: her etkenin katkısı, öteki
   etken iki yılın değerinde tutularak hesaplanan iki farkın ortalaması;
   katkıların toplamı toplam değişime tam eşittir).
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterstats

from core.cache import atomic_output_path
from core.city_config import CityConfig
from core.hvi import (
    CATEGORY_ORDER_5,
    combine_groups,
    group_scores,
    informative_components,
    pooled_group_bounds,
    rescale_groups,
    robust_bounds,
    scale_between,
)
from core.paths import city_data_proc, year_paths

DEFAULT_BUFFERS_M = (10, 30, 50)
TOP_SHARE = 0.10
HIGH_CATEGORIES = {"Kritik", "Aşırı Kritik"}
STATIC_COMPONENTS = [
    "exposure_norm", "sensitivity_yasli_norm", "sensitivity_cocuk_norm", "sensitivity_saglik_norm",
    "sensitivity_yesil_norm", "sensitivity_yapilasma_norm", "sensitivity_sosyoekonomik_norm",
]


def _static_table(roads: pd.DataFrame) -> pd.DataFrame:
    present = [c for c in STATIC_COMPONENTS if c in roads.columns]
    return roads[informative_components(roads, present)]


def scores_from_yearly(roads: pd.DataFrame, hazard: dict[str, pd.Series], tree: dict[str, pd.Series],
                       bounds: dict | None = None) -> tuple[dict[str, pd.Series], dict]:
    """Ana endeksin grup ve birleştirme adımlarıyla yıl başına HVI skoru.

    `hazard` ve `tree` yıl -> 0-1 ölçekli bileşen. `bounds` verilmezse grup
    sınırları verilen yılların ortak dağılımından hesaplanır (ana endeksle
    aynı); karşı-olgusal karışımlarda gerçek yılların sınırları verilir ki
    hepsi aynı cetvelle ölçülsün.
    """
    static = _static_table(roads)
    tables = {}
    for year in hazard:
        values = static.copy()
        values["hazard_norm"] = hazard[year]
        values["sensitivity_agac_norm"] = tree[year]
        complete = roads[[c for c in STATIC_COMPONENTS if c in roads.columns]].notna().all(axis=1)
        tables[year] = values.where(complete & values.notna().all(axis=1))
    bounds = bounds or pooled_group_bounds(list(tables.values()))
    return {year: combine_groups(rescale_groups(group_scores(t), bounds)) for year, t in tables.items()}, bounds


def _rank_pct(score: pd.Series) -> pd.Series:
    return score.rank(pct=True)


def _sample(roads_utm: gpd.GeoDataFrame, raster: Path, buffer_m: float) -> pd.Series:
    buffers = roads_utm.geometry.buffer(buffer_m)
    with_crs = gpd.GeoSeries(buffers, crs=roads_utm.crs)
    import rasterio

    with rasterio.open(raster) as src:
        shapes = with_crs.to_crs(src.crs)
    stats = rasterstats.zonal_stats(shapes, str(raster), stats=["mean"], nodata=-9999.0, all_touched=False)
    return pd.Series([s["mean"] for s in stats], index=roads_utm.index, dtype=float)


def buffer_sensitivity(config: CityConfig, roads: gpd.GeoDataFrame, years: list[str], main_year: str,
                       buffers_m: tuple[int, ...] = DEFAULT_BUFFERS_M) -> dict:
    """Her tampon için LST/NDVI'yi yeniden örnekleyip son yılın sırasını karşılaştırır."""
    roads_utm = roads.to_crs(config.crs)
    ranks = {}
    for buffer_m in buffers_m:
        lst, ndvi = {}, {}
        for year in years:
            _, proc = year_paths(config.city_id, year, main_year)
            lst[year] = _sample(roads_utm, proc / "lst_celsius.tif", buffer_m)
            ndvi[year] = _sample(roads_utm, proc / "ndvi.tif", buffer_m)
        # Ana hatla aynı cetvel: tüm yılların ortak %2-%98 aralığı (risk skoru
        # LST'nin doğrusal ölçeğidir, sağlam ölçekleme doğrusal dönüşüme duyarsız).
        lst_b = robust_bounds(pd.concat(lst.values()))
        ndvi_b = robust_bounds(pd.concat(ndvi.values()))
        hazard = {y: scale_between(lst[y], *lst_b) for y in years}
        tree = {y: 1 - scale_between(ndvi[y], *ndvi_b) for y in years}
        scores, _ = scores_from_yearly(roads, hazard, tree)
        ranks[buffer_m] = _rank_pct(scores[main_year])
        print(f"  {buffer_m} m tampon örneklendi")

    reference = min(buffers_m)
    table = pd.DataFrame({f"sira_{b}m": ranks[b] for b in buffers_m})
    valid = table.notna().all(axis=1)
    table = table[valid]
    summary_rows = []
    for buffer_m in buffers_m:
        if buffer_m == reference:
            continue
        a, b = table[f"sira_{reference}m"], table[f"sira_{buffer_m}m"]
        top_a, top_b = a > 1 - TOP_SHARE, b > 1 - TOP_SHARE
        table[f"sira_degisimi_{buffer_m}m"] = (b - a) * 100
        summary_rows.append({
            "tampon_m": buffer_m, "referans_m": reference, "yol_sayisi": int(len(table)),
            "spearman": round(float(a.corr(b)), 4),
            "ilk_yuzde10_ortusme": round(float((top_a & top_b).sum() / max(top_a.sum(), 1)), 4),
            "medyan_mutlak_sira_degisimi_puan": round(float((b - a).abs().median() * 100), 2),
            "20_puandan_fazla_degisen_pay": round(float(((b - a).abs() > 0.20).mean()), 4),
        })
    widest = max(buffers_m)
    change = f"sira_degisimi_{widest}m"
    meta = roads.loc[table.index, [c for c in ("name", "highway", "mahalle_adi", "ilce_adi") if c in roads.columns]]
    table = meta.join(table)
    by_type = None
    if "highway" in table:
        grouped = table.groupby("highway")[change]
        by_type = pd.DataFrame({
            "yol_sayisi": grouped.size(),
            "ort_sira_degisimi_puan": grouped.mean().round(2),
            "medyan_mutlak_degisim_puan": grouped.apply(lambda s: s.abs().median()).round(2),
        }).query("yol_sayisi >= 30").sort_values("ort_sira_degisimi_puan")
    return {"roads": table, "summary": pd.DataFrame(summary_rows), "by_type": by_type, "reference": reference,
            "widest": widest}


def temporal_decomposition(roads: pd.DataFrame, years: list[str]) -> dict:
    """İlk ve son yıl arasındaki HVI değişimini sıcaklık ve NDVI katkısına ayırır (Shapley)."""
    first, last = years[0], years[-1]
    hazard = {y: roads[f"hazard_norm_{y}"] for y in years}
    tree = {y: roads[f"sensitivity_agac_norm_{y}"] for y in years}
    actual, bounds = scores_from_yearly(roads, hazard, tree)
    mixes = {
        "h1_t0": ({"x": hazard[last]}, {"x": tree[first]}),
        "h0_t1": ({"x": hazard[first]}, {"x": tree[last]}),
    }
    counter = {name: scores_from_yearly(roads, h, t, bounds)[0]["x"] for name, (h, t) in mixes.items()}
    s0, s1 = actual[first], actual[last]
    # Yüzde ölçeği ana endeksteki gibi: tüm yılların ortak min-max'ı.
    pooled = pd.concat(actual.values()).dropna()
    to_pct = 100 / (pooled.max() - pooled.min())
    heat = 0.5 * ((counter["h1_t0"] - s0) + (s1 - counter["h0_t1"])) * to_pct
    tree_part = 0.5 * ((counter["h0_t1"] - s0) + (s1 - counter["h1_t0"])) * to_pct
    total = (s1 - s0) * to_pct
    table = pd.DataFrame({"toplam_degisim": total, "sicaklik_katkisi": heat, "ndvi_katkisi": tree_part})
    table = table.dropna()
    if "ilce_adi" in roads:
        table["ilce_adi"] = roads.loc[table.index, "ilce_adi"]

    published = roads.get(f"hvi_score_{last}")
    reproduction = float(s1.corr(published)) if published is not None else None
    cat0, cat1 = roads.get(f"hvi_category_{first}"), roads.get(f"hvi_category_{last}")
    transitions = None
    if cat0 is not None and cat1 is not None:
        known = cat0.isin(CATEGORY_ORDER_5) & cat1.isin(CATEGORY_ORDER_5)
        transitions = pd.crosstab(cat0[known], cat1[known]).reindex(
            index=CATEGORY_ORDER_5, columns=CATEGORY_ORDER_5, fill_value=0)
    summary = {
        "first_year": first, "last_year": last, "road_count": int(len(table)),
        "mean_total_change_pts": round(float(table["toplam_degisim"].mean()), 3),
        "mean_heat_contribution_pts": round(float(table["sicaklik_katkisi"].mean()), 3),
        "mean_ndvi_contribution_pts": round(float(table["ndvi_katkisi"].mean()), 3),
        "share_of_abs_change_from_heat": round(float(
            table["sicaklik_katkisi"].abs().sum()
            / (table["sicaklik_katkisi"].abs().sum() + table["ndvi_katkisi"].abs().sum())), 4),
        "reproduces_published_last_year_pearson": round(reproduction, 6) if reproduction is not None else None,
        "held_constant": ["nüfus (adapter'ın tek yıllık verisi)", "yaş yapısı", "SEGE-2022", "OSM bileşenleri"],
        "not_measured": "2020 nüfusuyla hesaplansaydı ne değişirdi: açık veride 2020 mahalle nüfusu yok",
    }
    by_district = None
    if "ilce_adi" in table:
        by_district = table.groupby("ilce_adi")[["toplam_degisim", "sicaklik_katkisi", "ndvi_katkisi"]].mean().round(2)
        by_district = by_district.sort_values("toplam_degisim", ascending=False)
    return {"roads": table, "summary": summary, "by_district": by_district, "transitions": transitions}


def write_sensitivity_outputs(config: CityConfig, roads: gpd.GeoDataFrame, buffers: dict | None,
                              temporal: dict | None, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or city_data_proc(config.city_id) / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    if buffers is not None:
        widest, change = buffers["widest"], f"sira_degisimi_{buffers['widest']}m"
        buffers["summary"].to_csv(output_dir / "tampon_ozet.csv", index=False)
        if buffers["by_type"] is not None:
            buffers["by_type"].to_csv(output_dir / "tampon_yol_tipi.csv")
        ranked = buffers["roads"].reindex(buffers["roads"][change].abs().sort_values(ascending=False).index)
        movers = gpd.GeoDataFrame(ranked.head(500).round(4), geometry=roads.loc[ranked.head(500).index].geometry,
                                  crs=roads.crs)
        with atomic_output_path(output_dir / "tampon_en_cok_degisen_yollar.geojson") as temporary:
            movers.to_file(temporary, driver="GeoJSON")
        summary["buffer"] = buffers["summary"].to_dict(orient="records")
        if buffers["by_type"] is not None:
            _plot_by_type(buffers["roads"], change, buffers["reference"], widest, output_dir / "tampon_yol_tipi.png")
    if temporal is not None:
        temporal["roads"].round(3).to_csv(output_dir / "zamansal_ayristirma_yollar.csv", index_label="yol_no")
        if temporal["by_district"] is not None:
            temporal["by_district"].to_csv(output_dir / "zamansal_ayristirma_ilce.csv")
        if temporal["transitions"] is not None:
            temporal["transitions"].to_csv(output_dir / "kategori_gecisleri.csv")
        summary["temporal"] = temporal["summary"]
    with atomic_output_path(output_dir / "duyarlilik_ozet.json") as temporary:
        temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return output_dir


def _plot_by_type(table: pd.DataFrame, change: str, reference: int, widest: int, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = table["highway"].value_counts()
    types = [t for t in counts.index if counts[t] >= 30]
    order = sorted(types, key=lambda t: table.loc[table["highway"] == t, change].median())
    data = [table.loc[table["highway"] == t, change].dropna().to_numpy() for t in order]
    fig, ax = plt.subplots(figsize=(8, 0.38 * len(order) + 1.6), dpi=150)
    ax.boxplot(data, vert=False, showfliers=False, widths=0.6)
    ax.set_yticks(np.arange(1, len(order) + 1), [f"{t} ({counts[t]:,})".replace(",", ".") for t in order])
    ax.axvline(0, color="#999999", lw=1)
    ax.set_xlabel(f"Sıra yüzdeliği değişimi, {reference} m'den {widest} m tampona (puan)")
    ax.set_title("Tampon genişleyince hangi yol tiplerinin sırası değişiyor?", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png")
    plt.close(fig)
