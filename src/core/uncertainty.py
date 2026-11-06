"""HVI sıralamasının belirsizlik ve küresel duyarlılık analizi (Monte Carlo).

HVI bir ölçüm değil, bir dizi tasarım kararının sonucudur: bileşenlerin
nasıl ölçekleneceği, grupların ve grup içi bileşenlerin ağırlığı, grupların
birbirini telafi edip edemeyeceği (geometrik ya da aritmetik ortalama),
geometrik ortalamanın tabanı, hatta hangi bileşenin endekse gireceği.
README bu kararların "bir yargı" olduğunu söylüyor; bu modül o yargının
sonuca ne kadar dokunduğunu ölçer.

Yöntem, bileşik göstergeler literatüründeki standart belirsizlik/duyarlılık
analizidir (OECD/JRC, "Handbook on Constructing Composite Indicators", 2008;
Saisana, Saltelli ve Tarantola, 2005, J. R. Stat. Soc. A 168(2)): her
koşuda kararlar kendi dağılımlarından rastgele çekilir, endeks yeniden
hesaplanır, yolların sırası kaydedilir.

Çıktılar:
  - Yol başına: sıra yüzdeliğinin medyanı ve %5-%95 aralığı, ilk %10 ve
    ilk %20 riskli dilime girme olasılığı. "Bu yol yüksek riskli" demenin
    tasarım kararlarına ne kadar dayanıklı olduğunu gösterir.
  - Mahalle başına: ortalama skora göre sıranın dağılımı (README'deki
    "en riskli 5 mahalle" listesinin kararlılığı).
  - Karar başına birinci derece duyarlılık indeksi S_i = Var(E[Y|X_i]) /
    Var(Y). Y, koşunun varsayılan endeksle Spearman korelasyonu ve ilk %10
    örtüşmesidir. Sürekli kararlar için koşullu beklenti 10 yüzdelik dilimde
    kestirilir; bu kestirici küçük örnekte yukarı yanlıdır (yaklaşık
    (dilim sayısı - 1) / koşu sayısı), bu yüzden 500 koşuda ~0,02'nin altı
    gürültü sayılmalıdır.

Belirsizlik kapsamı dışında kalanlar: yol tamponu genişliği (raster yeniden
örneklemesi gerektirir, `core/impact_analysis.py` 10/30/50 m ile ayrıca
ölçer) ve verinin kendi ölçüm hatası (Landsat LST, OSM eksikliği, nüfus).
Buradaki aralık bu yüzden bir alt sınırdır: yalnızca yöntem kararlarından
gelen belirsizliği gösterir.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from core.cache import atomic_output_path
from core.city_config import CityConfig
from core.hvi import COMPONENT_FLOOR, COMPONENT_GROUPS, ROBUST_QUANTILES, informative_components
from core.paths import city_data_proc

NORMALIZATIONS = ("robust", "minmax", "rank")
AGGREGATIONS = ("geometric", "arithmetic")

# Bileşenin ham kaynağı ve riske katkı yönü. Yönü -1 olanlar (NDVI,
# sosyoekonomik gelişmişlik) ölçeklenmeden önce ters çevrilir; ana endeksteki
# `1 - normalize(x)` ile aynı sırayı verir. Yıl bazlı kaynaklarda {year}
# yer tutucusu vardır.
RAW_SOURCES = {
    "hazard_norm": ("risk_score_{year}", 1),
    "sensitivity_agac_norm": ("ndvi_mean_{year}", -1),
    "exposure_norm": ("nufus_yogunlugu", 1),
    "sensitivity_yapilasma_norm": ("bina_yogunlugu", 1),
    "sensitivity_yasli_norm": ("yasli_oran", 1),
    "sensitivity_cocuk_norm": ("cocuk_oran", 1),
    "sensitivity_sosyoekonomik_norm": ("sosyoekonomik_skor", -1),
    "sensitivity_saglik_norm": ("dist_saglik_m", 1),
    "sensitivity_yesil_norm": ("dist_yesil_m", 1),
}
YEARLY_COMPONENTS = {"hazard_norm", "sensitivity_agac_norm"}

# README'deki mahalle sıralamasıyla aynı eşik: az yollu mahallenin ortalaması
# tek bir yolun değerine fazla bağlıdır.
MIN_SEGMENTS_PER_MAHALLE = 20
SENSITIVITY_BINS = 10


@dataclass(frozen=True)
class UncertaintySettings:
    """Kararların dağılımları. Varsayılanlar bir yargıdır ve rapora yazılır.

    `group_concentration`: grup ağırlıkları Dirichlet(c, c, c). c=8, her grubun
    ağırlığını yaklaşık %90 olasılıkla 0,19-0,49 arasında tutar: "üç grup
    kabaca eşit önemde" varsayımını korur ama birinin iki katı ağırlık
    almasına izin verir.
    `component_concentration`: grup içi bileşen ağırlıkları Dirichlet(c, ..., c).
    Daha küçük c, grup içinde daha serbest ağırlık demektir.
    `exclusion_probability`: bir koşuda bir bileşenin endeksten çıkarılma
    olasılığı (hangisi olduğu eşit olasılıkla seçilir). Tek üyeli grup
    (tehlike) çıkarılamaz, aksi halde endeks ısı endeksi olmaktan çıkar.
    """

    runs: int = 500
    seed: int = 42
    group_concentration: float = 8.0
    component_concentration: float = 4.0
    floor_range: tuple[float, float] = (0.01, 0.10)
    exclusion_probability: float = 0.25


def _pooled_scale(columns: list[np.ndarray], method: str) -> list[np.ndarray]:
    """Aynı bileşenin yıllara ait dizilerini TEK bir cetvelle 0-1'e çeker.

    Ana endeksteki ortak ölçek gerekçesiyle aynı (bkz. core/hvi.py): yıl
    başına ayrı ölçeklemek yıllar arası karşılaştırmayı bozardı.
    """
    pooled = np.concatenate(columns)
    finite = pooled[np.isfinite(pooled)]
    if finite.size == 0:
        return [np.full_like(column, np.nan) for column in columns]
    if method == "rank":
        # Ortak dağılımdaki yüzdelik sıra; eşitlerde ortalama sıra.
        ranks = pd.Series(pooled).rank(pct=True, method="average").to_numpy()
        return np.split(ranks, np.cumsum([len(c) for c in columns])[:-1])
    if method == "robust":
        low, high = np.quantile(finite, ROBUST_QUANTILES)
        if low == high:
            low, high = finite.min(), finite.max()
    else:
        low, high = finite.min(), finite.max()
    if high == low:
        return [np.where(np.isfinite(column), 0.0, np.nan) for column in columns]
    return [np.clip((column - low) / (high - low), 0, 1) for column in columns]


def _robust_bounds(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.nan, np.nan
    low, high = np.quantile(finite, ROBUST_QUANTILES)
    if low == high:
        low, high = finite.min(), finite.max()
    return float(low), float(high)


class _ComponentCube:
    """Yollar × bileşenler × yıllar; her ölçekleme yöntemi için bir kez kurulur."""

    def __init__(self, roads: pd.DataFrame, years: list[str]):
        self.years = years
        static = [c for c in RAW_SOURCES if c not in YEARLY_COMPONENTS and c in roads.columns]
        # Ana endeksle aynı seçim: tüm yollarda sabit olan bileşen ayırt etmez.
        static = informative_components(roads, static)
        self.components = ["hazard_norm", "sensitivity_agac_norm", *static]
        self.groups = {
            group: [i for i, c in enumerate(self.components) if c in members]
            for group, members in COMPONENT_GROUPS.items()
        }
        self.groups = {g: idx for g, idx in self.groups.items() if idx}

        self.tables: dict[str, list[np.ndarray]] = {}
        for method in NORMALIZATIONS:
            per_component = []
            for component in self.components:
                stored = [f"{component}_{year}" if component in YEARLY_COMPONENTS else component for year in years]
                if method == "robust" and all(column in roads.columns for column in stored):
                    # Ana endeksin kendi ölçeklediği sütunlar: varsayılan koşu
                    # yayımlanan skoru birebir yeniden üretir (sınırlar ana
                    # endekste tüm yollardan hesaplanmıştır, burada yalnızca
                    # skorlu yollar var).
                    per_component.append([pd.to_numeric(roads[c], errors="coerce").to_numpy(float) for c in stored])
                    continue
                source, direction = RAW_SOURCES[component]
                raw = [
                    direction * pd.to_numeric(roads[source.format(year=year)], errors="coerce").to_numpy(float)
                    for year in years
                ]
                per_component.append(_pooled_scale(raw, method))
            # [yıl] -> (yol, bileşen)
            self.tables[method] = [
                np.column_stack([per_component[k][y] for k in range(len(self.components))])
                for y in range(len(years))
            ]


def sample_settings(cube: _ComponentCube, settings: UncertaintySettings, rng: np.random.Generator,
                    runs: int) -> list[dict[str, Any]]:
    """Her koşu için bir karar kümesi çeker. İlk koşu ana endeksin kendisidir."""
    groups = list(cube.groups)
    excludable = [
        cube.components[i] for idx in cube.groups.values() if len(idx) > 1 for i in idx
    ]
    draws = [{
        "normalization": "robust", "aggregation": "geometric", "floor": COMPONENT_FLOOR,
        "excluded": None,
        "group_weights": {g: 1 / len(groups) for g in groups},
        "component_weights": {c: 1.0 for c in cube.components},
    }]
    for _ in range(runs - 1):
        group_w = rng.dirichlet([settings.group_concentration] * len(groups))
        component_w = {}
        for idx in cube.groups.values():
            if len(idx) == 1:
                # Tek üyeli grupta (tehlike) ağırlık tanım gereği 1'dir; Dirichlet
                # tek parametreyle bit düzeyinde 1 döndürmediği için sahte bir
                # "karar" gibi duyarlılık tablosuna sızıyordu.
                component_w[cube.components[idx[0]]] = 1.0
                continue
            w = rng.dirichlet([settings.component_concentration] * len(idx)) * len(idx)
            component_w.update({cube.components[i]: float(v) for i, v in zip(idx, w, strict=True)})
        excluded = None
        if excludable and rng.random() < settings.exclusion_probability:
            excluded = str(rng.choice(excludable))
        draws.append({
            "normalization": str(rng.choice(NORMALIZATIONS)),
            "aggregation": str(rng.choice(AGGREGATIONS)),
            "floor": float(rng.uniform(*settings.floor_range)),
            "excluded": excluded,
            "group_weights": dict(zip(groups, map(float, group_w), strict=True)),
            "component_weights": component_w,
        })
    return draws


def score_run(cube: _ComponentCube, draw: dict[str, Any]) -> list[np.ndarray]:
    """Bir karar kümesiyle her yılın skorunu (0-100) üretir.

    Adımlar ana endeksle aynıdır (bkz. core/hvi.py): grup içi ağırlıklı
    aritmetik ortalama, grup skorlarının yıllar ortak %2-%98 yeniden
    ölçeklenmesi, gruplar arası birleştirme.
    """
    tables = cube.tables[draw["normalization"]]
    group_scores: dict[str, list[np.ndarray]] = {}
    for group, idx in cube.groups.items():
        members = [i for i in idx if cube.components[i] != draw["excluded"]]
        w = np.asarray([draw["component_weights"][cube.components[i]] for i in members], dtype=float)
        w = w / w.sum()
        group_scores[group] = [table[:, members] @ w for table in tables]

    rescaled = {}
    for group, per_year in group_scores.items():
        low, high = _robust_bounds(np.concatenate(per_year))
        if not (np.isfinite(low) and np.isfinite(high)) or high == low:
            rescaled[group] = [np.where(np.isfinite(s), 0.0, np.nan) for s in per_year]
        else:
            rescaled[group] = [np.clip((s - low) / (high - low), 0, 1) for s in per_year]

    names = list(rescaled)
    gw = np.asarray([draw["group_weights"][g] for g in names], dtype=float)
    gw = gw / gw.sum()
    scores = []
    for y in range(len(cube.years)):
        stacked = np.column_stack([rescaled[g][y] for g in names])
        if draw["aggregation"] == "geometric":
            floor = draw["floor"]
            scores.append(np.exp(np.log(floor + (1 - floor) * stacked) @ gw) * 100)
        else:
            scores.append(stacked @ gw * 100)
    return scores


def _rank_pct(values: np.ndarray) -> np.ndarray:
    return pd.Series(values).rank(pct=True, method="average").to_numpy(dtype="float32")


def _top_overlap(base_pct: np.ndarray, run_pct: np.ndarray, share: float) -> float:
    base_top = base_pct > 1 - share
    return float((base_top & (run_pct > 1 - share)).sum() / max(base_top.sum(), 1))


def first_order_indices(factors: pd.DataFrame, outputs: pd.DataFrame,
                        bins: int = SENSITIVITY_BINS) -> pd.DataFrame:
    """Her karar için birinci derece duyarlılık indeksi S_i = Var(E[Y|X_i]) / Var(Y).

    Kategorik kararlar (metin sütunları) kendi düzeylerine, sürekli kararlar
    `bins` yüzdelik dilime göre gruplanır. Bağımlılık eklememek için
    Saltelli tasarımı yerine bu "binning" kestiricisi kullanılır; varsayılan
    500 koşu ile sıralamayı ayırt etmeye yeter (yanlılık modül docstring'inde).
    """
    rows = []
    for factor in factors.columns:
        x = factors[factor]
        if x.dtype == object or x.nunique() <= bins:
            key = x.astype(str)
        else:
            key = pd.qcut(x, q=bins, duplicates="drop").astype(str)
        for output in outputs.columns:
            y = outputs[output]
            total = y.var(ddof=0)
            if not np.isfinite(total) or total == 0:
                s = 0.0
            else:
                means = y.groupby(key).agg(["mean", "size"])
                s = float(((means["mean"] - y.mean()) ** 2 * means["size"]).sum() / len(y) / total)
            rows.append({"karar": factor, "cikti": output, "S_i": round(s, 4)})
    table = pd.DataFrame(rows).pivot(index="karar", columns="cikti", values="S_i")
    return table.sort_values(table.columns[0], ascending=False)


def _factor_table(draws: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for draw in draws:
        row = {
            "olcekleme": draw["normalization"],
            "birlestirme": draw["aggregation"],
            "taban": draw["floor"],
            "dislanan_bilesen": draw["excluded"] or "yok",
        }
        row.update({f"grup_agirligi:{g}": w for g, w in draw["group_weights"].items()})
        row.update({f"bilesen_agirligi:{c}": w for c, w in draw["component_weights"].items()})
        rows.append(row)
    table = pd.DataFrame(rows)
    # Tek üyeli grubun (tehlike) bileşen ağırlığı her koşuda 1'dir, bilgi taşımaz.
    constant = [c for c in table.columns if table[c].nunique() <= 1]
    return table.drop(columns=constant)


def run_uncertainty(roads: gpd.GeoDataFrame, years: list[str], main_year: str,
                    settings: UncertaintySettings | None = None) -> dict[str, Any]:
    """Monte Carlo analizini yürütür; yol/mahalle tablolarını ve özeti döndürür.

    Yalnızca tüm yıllarda ana endeks skoru olan yollar kullanılır: eksik
    bileşenli yol ana endekste de skor almaz.
    """
    settings = settings or UncertaintySettings()
    if settings.runs < 2:
        raise ValueError("En az iki koşu gerekli (ilki varsayılan endekstir).")
    years = [str(y) for y in years]
    main_year = str(main_year)
    valid = np.logical_and.reduce([roads[f"hvi_score_{y}"].notna().to_numpy() for y in years])
    data = roads.loc[valid]
    if len(data) < 10:
        raise ValueError(f"Belirsizlik analizi için yeterli skorlu yol yok ({len(data)}).")

    cube = _ComponentCube(data, years)
    main_index = years.index(main_year)
    rng = np.random.default_rng(settings.seed)
    draws = sample_settings(cube, settings, rng, settings.runs)

    mahalle_key = None
    if "mahalle_adi" in data.columns:
        key = data["mahalle_adi"].astype(str) + " (" + data.get("ilce_adi", pd.Series("", index=data.index)).astype(str) + ")"
        counts = key.value_counts()
        kept = counts[counts >= MIN_SEGMENTS_PER_MAHALLE].index
        mahalle_key = key.where(key.isin(kept))

    n = len(data)
    rank_pct = np.empty((settings.runs, n), dtype="float32")
    mahalle_ranks = []
    outputs = []
    base_pct = None
    reproduction = None
    for r, draw in enumerate(draws):
        score = score_run(cube, draw)[main_index]
        pct = _rank_pct(score)
        rank_pct[r] = pct
        if r == 0:
            base_pct = pct
            # Bu modül endeksi ham bileşenlerden yeniden kurar; varsayılan koşu
            # yayımlanan skorla aynı sırayı vermiyorsa analiz başka bir endeksi
            # ölçüyor demektir.
            reproduction = float(pd.Series(score).corr(data[f"hvi_score_{main_year}"].reset_index(drop=True),
                                                       method="pearson"))
        outputs.append({
            "spearman": float(np.corrcoef(base_pct, pct)[0, 1]),
            "ilk_yuzde10_ortusme": _top_overlap(base_pct, pct, 0.10),
        })
        if mahalle_key is not None:
            means = pd.Series(score, index=data.index).groupby(mahalle_key).mean()
            mahalle_ranks.append(means.rank(ascending=False, method="min"))

    roads_out = pd.DataFrame({
        "sira_varsayilan": base_pct,
        "sira_medyan": np.median(rank_pct, axis=0),
        "sira_p05": np.quantile(rank_pct, 0.05, axis=0),
        "sira_p95": np.quantile(rank_pct, 0.95, axis=0),
        "olasilik_ilk_yuzde10": (rank_pct > 0.90).mean(axis=0),
        "olasilik_ilk_yuzde20": (rank_pct > 0.80).mean(axis=0),
    }, index=data.index).astype("float32")
    roads_out["sira_bandi"] = roads_out["sira_p95"] - roads_out["sira_p05"]
    del rank_pct

    mahalle_out = None
    if mahalle_ranks:
        ranks = pd.concat(mahalle_ranks, axis=1)
        mahalle_out = pd.DataFrame({
            "yol_sayisi": mahalle_key.value_counts(),
            "sira_varsayilan": ranks.iloc[:, 0],
            "sira_medyan": ranks.median(axis=1),
            "sira_p05": ranks.quantile(0.05, axis=1),
            "sira_p95": ranks.quantile(0.95, axis=1),
            "olasilik_ilk_5": (ranks <= 5).mean(axis=1),
            "olasilik_ilk_20": (ranks <= 20).mean(axis=1),
        }).sort_values("sira_varsayilan")
        mahalle_out.index.name = "mahalle"

    outputs = pd.DataFrame(outputs)
    factors = _factor_table(draws)
    # Varsayılan koşu tasarımın bir parçası değil, referanstır: indekslere girmez.
    sensitivity = first_order_indices(factors.iloc[1:].reset_index(drop=True),
                                      outputs.iloc[1:].reset_index(drop=True))

    perturbed = outputs.iloc[1:]
    stable_top = roads_out["olasilik_ilk_yuzde10"] >= 0.9
    base_top = roads_out["sira_varsayilan"] > 0.90
    summary = {
        "year": main_year,
        "years_pooled": years,
        "road_count": int(n),
        "components": cube.components,
        "settings": asdict(settings),
        "default_run_reproduces_published_index_pearson": round(reproduction, 6),
        "spearman_vs_default": _quantiles(perturbed["spearman"]),
        "top10_overlap_vs_default": _quantiles(perturbed["ilk_yuzde10_ortusme"]),
        "road_rank_band_p05_p95": _quantiles(roads_out["sira_bandi"]),
        "default_top10_roads": int(base_top.sum()),
        "default_top10_roads_stable_ge_90pct": int((base_top & stable_top).sum()),
        "share_of_default_top10_stable_ge_90pct": round(float((base_top & stable_top).sum() / max(base_top.sum(), 1)), 4),
        "sensitivity_first_order": sensitivity.round(4).reset_index().to_dict(orient="records"),
    }
    return {"roads": roads_out, "mahalle": mahalle_out, "sensitivity": sensitivity,
            "runs": pd.concat([factors, outputs], axis=1), "summary": summary}


def _quantiles(series: pd.Series) -> dict[str, float]:
    return {f"p{int(q * 100):02d}": round(float(series.quantile(q)), 4) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}


def write_uncertainty_outputs(config: CityConfig, roads: gpd.GeoDataFrame, result: dict[str, Any],
                              output_dir: Path | None = None) -> Path:
    """Sonuçları `data/processed/<sehir>/uncertainty/` altına yazar."""
    output_dir = output_dir or city_data_proc(config.city_id) / "uncertainty"
    output_dir.mkdir(parents=True, exist_ok=True)
    year = result["summary"]["year"]

    keep = [c for c in ("mahalle_adi", "ilce_adi", f"hvi_percentage_{year}", f"hvi_category_{year}")
            if c in roads.columns]
    # `yol_no`, girdi tablosundaki satır konumudur; GeoJSON indeksi taşımadığı
    # için veri paketi (core/export.py) yolları bununla eşler.
    positions = pd.Series(np.arange(len(roads)), index=roads.index).loc[result["roads"].index]
    road_gdf = gpd.GeoDataFrame(
        roads.loc[result["roads"].index, keep].assign(yol_no=positions.to_numpy()).join(result["roads"].round(4)),
        geometry=roads.loc[result["roads"].index].geometry, crs=roads.crs,
    )
    with atomic_output_path(output_dir / "belirsizlik_yollar.geojson") as temporary:
        road_gdf.to_file(temporary, driver="GeoJSON")
    if result["mahalle"] is not None:
        with atomic_output_path(output_dir / "belirsizlik_mahalleler.csv") as temporary:
            result["mahalle"].round(4).to_csv(temporary)
    with atomic_output_path(output_dir / "belirsizlik_duyarlilik.csv") as temporary:
        result["sensitivity"].to_csv(temporary)
    with atomic_output_path(output_dir / "belirsizlik_kosular.csv") as temporary:
        result["runs"].round(5).to_csv(temporary, index_label="kosu")
    with atomic_output_path(output_dir / "belirsizlik_ozet.json") as temporary:
        temporary.write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    return output_dir
