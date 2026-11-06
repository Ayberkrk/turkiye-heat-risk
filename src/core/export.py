"""Şehir veri paketi: harita dışındaki herkes için indirilebilir çıktılar.

Web haritası sorulara tek tek yol tıklayarak cevap verir; bir belediye
çalışanı, gazeteci ya da araştırmacı ise genelde bir tablo, kendi CBS
yazılımına alabileceği bir katman ya da bir rapora koyabileceği bir görsel
ister. Bu modül ana pipeline çıktısından (`roads_with_hvi.geojson`) ve
varsa belirsizlik analizinden şunları üretir:

  - `<şehir>_isi_riski.xlsx`: Özet, Mahalleler, İlçeler, Öncelikli yollar,
    (varsa) Belirsizlik, Sütun sözlüğü, Kaynaklar ve lisans sayfaları.
  - CSV kopyaları (UTF-8, virgül ayraçlı, nokta ondalık): Excel kullanıcısı
    çalışma kitabını açar; CSV, kod ve istatistik yazılımı içindir.
  - `<şehir>_isi_riski.gpkg`: yollar ve (adapter'dan) mahalle poligonları;
    QGIS, ArcGIS ve NetCAD tek dosya olarak açar.
  - PNG görseller ve yazdırılabilir tek sayfalık `ozet.html`.

Paket `output/<şehir>/paket/` altına yazılır ve zip'lenir (GitHub Release
için). Küçük dosyalar (Excel, mahalle/ilçe CSV'leri, görseller, özet)
ayrıca `docs/<şehir>/indir/` altına kopyalanır; GitHub Pages bunları
doğrudan sunar. Yol katmanı büyük olduğu için yalnızca zip'te bulunur.

Lisans: yol geometrileri ve OSM'den türetilen öznitelikler OpenStreetMap
verisinin türevidir; paket bu yüzden ODbL 1.0 altındadır (bkz.
`SOURCES`). Bu bir tercih değil, OSM lisansının türev veritabanları için
koşuludur.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from core.cache import atomic_output_path
from core.city_config import CityConfig, load_population_adapter
from core.hvi import CATEGORY_COLORS_5, CATEGORY_ORDER_5, HVI_FORMULA_VERSION
from core.paths import DOCS_DIR, OUTPUT_DIR, PROJECT_ROOT, city_data_proc, resolve_pbf_path

REPO_URL = "https://github.com/Ayberkrk/turkiye-heat-risk"
SITE_URL = "https://ayberkrk.github.io/turkiye-heat-risk"
# Release varlıkları sürümden bağımsız bu adresten indirilebilir; site
# bağlantıları her sürümde güncellenmek zorunda kalmaz.
RELEASE_DOWNLOAD_URL = f"{REPO_URL}/releases/latest/download"

# README'deki mahalle sıralamasıyla aynı eşik: az yollu mahallenin ortalaması
# tek bir yolun değerine fazla bağlıdır. Daha az yollu mahalleler tabloda
# kalır ama `guvenilir_ortalama` sütunu Hayır olur.
MIN_SEGMENTS_PER_MAHALLE = 20
PRIORITY_ROAD_COUNT = 1000
HIGH_CATEGORIES = ["Kritik", "Aşırı Kritik"]

DISCLAIMER = (
    "Bu endeks bir önceliklendirme aracıdır: sağlık verisiyle (acil başvuru, ölüm) doğrulanmamıştır. "
    "Bir yolun ya da mahallenin ötekinden kaç kat daha tehlikeli olduğunu değil, sıcak havada "
    "nereye önce bakılması gerektiğini gösterir. Skorlar şehrin kendi dağılımına göredir; iki "
    "şehrin aynı kategorisi aynı mutlak riski ifade etmez."
)

SOURCES = [
    ("Yüzey sıcaklığı ve NDVI", "Landsat 8/9 Collection 2 Level-2, USGS; Microsoft Planetary Computer üzerinden",
     "Kamu malı (USGS)"),
    ("Yol ağı, bina, sağlık tesisi, yeşil alan", "© OpenStreetMap katkıcıları", "ODbL 1.0"),
    ("Nüfus ızgarası", "Meta & CIESIN, High Resolution Settlement Layer", "CC BY 4.0"),
    ("Mahalle/ilçe nüfusu ve yaş yapısı", "Şehre göre: belediye açık veri portalı ya da TÜİK ADNKS",
     "Kaynağın kullanım koşulları"),
    ("Sosyoekonomik gelişmişlik", "T.C. Sanayi ve Teknoloji Bakanlığı, İlçelerin SEGE-2022 araştırması",
     "Kamuya açık resmi rapor"),
    ("Gece yüzey sıcaklığı (isteğe bağlı)", "MODIS MOD11A2/MYD11A2, NASA LP DAAC", "Kamu malı (NASA)"),
    ("Bu paket", f"turkiye-heat-risk, {REPO_URL}",
     "ODbL 1.0 (OSM türevi veritabanı); kod MIT"),
]

# Dışa aktarılan sütunların Türkçe açıklaması ve birimi. Yıl eki taşıyan
# sütunlar `{year}` ile yazılır. Burada olmayan sütun pakete girmez: iç
# yardımcı sütunlar (`_label_*`, `geometry_buffer`) kullanıcıya gösterilmez.
COLUMN_DICTIONARY = {
    "osm_ad": ("Yolun OSM'deki adı (varsa)", ""),
    "yol_tipi": ("OSM highway etiketi (primary, residential...)", ""),
    "uzunluk_m": ("Yol segmentinin uzunluğu", "m"),
    "mahalle_adi": ("Yolun orta noktasının düştüğü mahalle", ""),
    "ilce_adi": ("Mahallenin ilçesi", ""),
    "enlem": ("Yol orta noktasının enlemi", "derece (WGS84)"),
    "boylam": ("Yol orta noktasının boylamı", "derece (WGS84)"),
    "hvi_yuzde_{year}": ("Isı Hassasiyet Endeksi, yılların ortak ölçeğinde", "0-100"),
    "hvi_kategori_{year}": ("HVI kategorisi (yılların ortak Jenks sınırları)", "Düşük ... Aşırı Kritik"),
    "grup_tehlike_{year}": ("Tehlike grup skoru (yüzey sıcaklığı)", "0-1"),
    "grup_maruziyet_{year}": ("Maruziyet grup skoru (nüfus ve bina yoğunluğu)", "0-1"),
    "grup_kirilganlik_{year}": ("Kırılganlık grup skoru (yaş, sosyoekonomik, erişim, ağaç örtüsü)", "0-1"),
    "lst_ort_{year}": ("Yol tamponundaki ortalama yüzey sıcaklığı (hava sıcaklığı değil)", "°C"),
    "ndvi_ort_{year}": ("Yol tamponundaki ortalama NDVI (bitki örtüsü)", "-1 ile 1"),
    "nufus_yogunlugu": ("Yolun 150 m çevresindeki nüfus yoğunluğu (resmi nüfusa kalibre 30 m ızgara)",
                        "kişi/km²"),
    "nufus_yogunlugu_birim": ("Mahalle ya da ilçe düzeyindeki resmi nüfus yoğunluğu", "kişi/km²"),
    "bina_yogunlugu": ("Yolun 150 m çevresindeki OSM bina yoğunluğu", "bina/km²"),
    "yasli_oran": ("65 yaş ve üstü nüfus oranı (ilçe düzeyi)", "0-1"),
    "cocuk_oran": ("0-14 yaş nüfus oranı (ilçe düzeyi)", "0-1"),
    "sosyoekonomik_skor": ("SEGE-2022 ilçe gelişmişlik skoru (yüksek = gelişmiş)", "standart skor"),
    "dist_saglik_m": ("En yakın OSM sağlık tesisine düz çizgi mesafesi", "m"),
    "dist_yesil_m": ("En yakın OSM park/orman/çayır alanına düz çizgi mesafesi", "m"),
    "yol_sayisi": ("Birimdeki yol segmenti sayısı", "adet"),
    "toplam_yol_km": ("Birimdeki yolların toplam uzunluğu", "km"),
    "hvi_ort_{year}": ("Birimdeki yolların ortalama HVI'si", "0-100"),
    "yuksek_risk_payi_{year}": ("Birimdeki yolların Kritik ya da Aşırı Kritik olan payı", "0-1"),
    "hvi_degisim": ("Ortalama HVI'nin ilk yıldan son yıla değişimi", "puan"),
    "sira": ("Ortalama HVI'ye göre şehir içi sıra (1 = en riskli)", ""),
    "guvenilir_ortalama": (f"Birimde en az {MIN_SEGMENTS_PER_MAHALLE} yol var mı", "Evet/Hayır"),
    "olasilik_ilk_yuzde10": ("Belirsizlik analizinde yolun en riskli %10'da kalma olasılığı", "0-1"),
    "sira_p05": ("Belirsizlik analizinde sıra yüzdeliğinin %5 değeri", "0-1"),
    "sira_p95": ("Belirsizlik analizinde sıra yüzdeliğinin %95 değeri", "0-1"),
    "olasilik_ilk_5": ("Belirsizlik analizinde mahallenin en riskli 5 mahalle arasında kalma olasılığı", "0-1"),
    "olasilik_ilk_20": ("Belirsizlik analizinde mahallenin en riskli 20 mahalle arasında kalma olasılığı",
                        "0-1"),
    "sira_medyan": ("Belirsizlik analizinde mahalle sırasının medyanı", ""),
}

# roads_with_hvi.geojson sütunu -> paket sütunu. Kullanıcıya dönük adlar
# Türkçe ve kendi kendini açıklar; iç adlar (group_exposure_2026) değil.
_ROAD_RENAMES = {
    "name": "osm_ad", "highway": "yol_tipi", "length": "uzunluk_m",
    "mahalle_adi": "mahalle_adi", "ilce_adi": "ilce_adi",
    "nufus_yogunlugu": "nufus_yogunlugu", "nufus_yogunlugu_birim": "nufus_yogunlugu_birim",
    "bina_yogunlugu": "bina_yogunlugu", "yasli_oran": "yasli_oran", "cocuk_oran": "cocuk_oran",
    "sosyoekonomik_skor": "sosyoekonomik_skor", "dist_saglik_m": "dist_saglik_m", "dist_yesil_m": "dist_yesil_m",
}
_YEAR_RENAMES = {
    "hvi_percentage_{year}": "hvi_yuzde_{year}", "hvi_category_{year}": "hvi_kategori_{year}",
    "group_hazard_{year}": "grup_tehlike_{year}", "group_exposure_{year}": "grup_maruziyet_{year}",
    "group_vulnerability_{year}": "grup_kirilganlik_{year}",
    "lst_mean_{year}": "lst_ort_{year}", "ndvi_mean_{year}": "ndvi_ort_{year}",
}


def citation_text(city_name: str) -> str:
    """Atıf satırı CITATION.cff'ten üretilir; yazar, sürüm ve DOI tek yerde tutulur."""
    try:
        cff = yaml.safe_load((PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        cff = {}
    authors = ", ".join(
        f"{a.get('family-names', '')}, {a.get('given-names', ' ')[0]}." for a in cff.get("authors", [])
    ) or "turkiye-heat-risk"
    year = str(cff.get("date-released", ""))[:4]
    version = f" (sürüm {cff['version']})" if cff.get("version") else ""
    doi = f" https://doi.org/{cff['doi']}" if cff.get("doi") else ""
    title = cff.get("title", "turkiye-heat-risk")
    return f"{authors} ({year}). {title}{version}. {city_name} veri paketi. {REPO_URL}{doi}"


def package_dir(config: CityConfig) -> Path:
    return OUTPUT_DIR / config.city_id / "paket"


def detect_years(roads: pd.DataFrame) -> list[str]:
    return sorted({m.group(1) for c in roads.columns if (m := re.fullmatch(r"hvi_score_(\d{4})", c))}, key=int)


def tidy_roads(roads: gpd.GeoDataFrame, years: list[str]) -> gpd.GeoDataFrame:
    """Yol tablosunu kullanıcıya dönük sütun adları ve yuvarlanmış değerlerle döndürür."""
    renames = {k: v for k, v in _ROAD_RENAMES.items() if k in roads.columns}
    for year in years:
        for source, target in _YEAR_RENAMES.items():
            if source.format(year=year) in roads.columns:
                renames[source.format(year=year)] = target.format(year=year)
    out = roads[list(renames)].rename(columns=renames)
    centroids = roads.to_crs(roads.estimate_utm_crs()).geometry.centroid.to_crs("EPSG:4326")
    out.insert(out.columns.get_loc("ilce_adi") + 1 if "ilce_adi" in out else 0, "enlem", centroids.y.round(6))
    out.insert(out.columns.get_loc("enlem") + 1, "boylam", centroids.x.round(6))
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            digits = 4 if column.startswith(("grup_", "yasli", "cocuk", "ndvi", "sosyo")) else 1
            out[column] = out[column].round(digits)
    return gpd.GeoDataFrame(out, geometry=roads.geometry, crs=roads.crs)


def area_table(roads: pd.DataFrame, years: list[str], by: list[str]) -> pd.DataFrame:
    """Mahalle ya da ilçe özeti: yol sayısı/uzunluğu, ortalama HVI, yüksek risk payı, değişim."""
    valid = roads.dropna(subset=[f"hvi_yuzde_{years[-1]}", *by])
    grouped = valid.groupby(by, sort=False)
    table = pd.DataFrame({"yol_sayisi": grouped.size(),
                          "toplam_yol_km": grouped["uzunluk_m"].sum() / 1000 if "uzunluk_m" in valid else np.nan})
    for year in years:
        table[f"hvi_ort_{year}"] = grouped[f"hvi_yuzde_{year}"].mean()
        table[f"yuksek_risk_payi_{year}"] = grouped[f"hvi_kategori_{year}"].agg(
            lambda s: s.isin(HIGH_CATEGORIES).mean()
        )
    if len(years) > 1:
        table["hvi_degisim"] = table[f"hvi_ort_{years[-1]}"] - table[f"hvi_ort_{years[0]}"]
    for year in years:
        for column in (f"lst_ort_{year}", f"ndvi_ort_{year}"):
            if column in valid:
                table[column] = grouped[column].mean()
    for column in ("nufus_yogunlugu", "yasli_oran", "cocuk_oran", "sosyoekonomik_skor", "dist_saglik_m", "dist_yesil_m"):
        if column in valid:
            table[column] = grouped[column].median()
    table = table.sort_values(f"hvi_ort_{years[-1]}", ascending=False)
    table.insert(0, "sira", range(1, len(table) + 1))
    table["guvenilir_ortalama"] = np.where(table["yol_sayisi"] >= MIN_SEGMENTS_PER_MAHALLE, "Evet", "Hayır")
    table = table.reset_index()
    for column in table.columns:
        if pd.api.types.is_float_dtype(table[column]):
            digits = 4 if column.startswith(("yuksek", "yasli", "cocuk", "ndvi", "sosyo")) else 1
            table[column] = table[column].round(digits)
    return table


def priority_roads(roads: gpd.GeoDataFrame, year: str, count: int = PRIORITY_ROAD_COUNT) -> pd.DataFrame:
    table = pd.DataFrame(roads.drop(columns=roads.geometry.name))
    table = table.dropna(subset=[f"hvi_yuzde_{year}"]).sort_values(f"hvi_yuzde_{year}", ascending=False).head(count)
    table.insert(0, "sira", range(1, len(table) + 1))
    return table.reset_index(drop=True)


def column_dictionary(columns: list[str]) -> pd.DataFrame:
    rows = []
    for column in columns:
        key = re.sub(r"_(\d{4})$", "_{year}", column)
        description, unit = COLUMN_DICTIONARY.get(key, COLUMN_DICTIONARY.get(column, ("", "")))
        if description:
            rows.append({"sutun": column, "aciklama": description, "birim": unit})
    return pd.DataFrame(rows).drop_duplicates("sutun")


def summary_rows(config: CityConfig, roads: pd.DataFrame, mahalle: pd.DataFrame, years: list[str],
                 uncertainty: dict | None) -> list[tuple[str, str]]:
    main = years[-1]
    valid = roads[f"hvi_yuzde_{main}"].notna()
    rows = [
        ("Şehir", config.name),
        ("Yıllar", ", ".join(years)),
        ("Skorlanan yol segmenti", f"{int(valid.sum()):,}".replace(",", ".")),
        ("Toplam yol uzunluğu (km)", f"{roads.loc[valid, 'uzunluk_m'].sum() / 1000:,.0f}".replace(",", ".")),
    ]
    for year in years:
        if f"lst_ort_{year}" in roads:
            rows.append((f"Ortalama yol yüzey sıcaklığı {year} (°C)", f"{roads[f'lst_ort_{year}'].mean():.1f}"))
    for year in years:
        counts = roads.loc[valid, f"hvi_kategori_{year}"].value_counts()
        rows.append((f"Kategori dağılımı {year}", ", ".join(f"{c}: {int(counts.get(c, 0))}" for c in CATEGORY_ORDER_5)))
    reliable = mahalle[mahalle["guvenilir_ortalama"] == "Evet"].head(5)
    rows.append(("En yüksek ortalama HVI'li 5 mahalle",
                 "; ".join(f"{r.mahalle_adi} ({r.ilce_adi}) %{r[f'hvi_ort_{main}']:.1f}" for _, r in reliable.iterrows())))
    if uncertainty:
        rows.append(("Belirsizlik: varsayılan ilk %10'un kararlı payı",
                     f"%{uncertainty['share_of_default_top10_stable_ge_90pct'] * 100:.0f} "
                     "(koşuların en az %90'ında yine ilk %10'da)"))
        rows.append(("Belirsizlik: Spearman medyanı (varsayılana göre)", str(uncertainty["spearman_vs_default"]["p50"])))
    rows += [
        ("HVI formül sürümü", str(HVI_FORMULA_VERSION)),
        ("Nüfus ızgarası", config.population_grid_url or "kullanılmadı (birim yoğunluğu)"),
        ("Üretim tarihi (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M")),
        ("Canlı harita", f"{SITE_URL}/{config.city_id}/"),
        ("Önemli uyarı", DISCLAIMER),
    ]
    return rows


def _style_workbook(path: Path) -> None:
    """Başlık satırını kalın yapar, ilk satırı dondurur, filtre ve sütun genişliği ekler."""
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="F2E6D9")
    for sheet in workbook.worksheets:
        if sheet.max_row < 1:
            continue
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
        if sheet.title not in ("Özet", "Kaynaklar ve lisans"):
            sheet.auto_filter.ref = sheet.dimensions
        for column_cells in sheet.columns:
            longest = max((len(str(c.value)) for c in column_cells[:200] if c.value is not None), default=8)
            limit = 90 if sheet.title in ("Özet", "Kaynaklar ve lisans", "Sütun sözlüğü") else 40
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(10, longest + 2), limit)
        if sheet.title in ("Özet", "Kaynaklar ve lisans", "Sütun sözlüğü"):
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(path)


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with atomic_output_path(path) as temporary:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name[:31], index=False)
        _style_workbook(temporary)


def _plot_map(roads: gpd.GeoDataFrame, mahalle_polys: gpd.GeoDataFrame | None, year: str, title: str,
              path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    crs = roads.estimate_utm_crs()
    projected = roads.to_crs(crs)
    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=150)
    if mahalle_polys is not None and len(mahalle_polys):
        mahalle_polys.to_crs(crs).boundary.plot(ax=ax, color="#bdbdbd", linewidth=0.3, zorder=1)
    category = projected[f"hvi_kategori_{year}"]
    missing = ~category.isin(CATEGORY_ORDER_5)
    if missing.any():
        projected[missing].plot(ax=ax, color="#e0e0e0", linewidth=0.3, zorder=2)
    for order, name in enumerate(CATEGORY_ORDER_5):
        subset = projected[category == name]
        if len(subset):
            subset.plot(ax=ax, color=CATEGORY_COLORS_5[name], linewidth=0.35 + 0.15 * order, zorder=3 + order)
    ax.set_axis_off()
    ax.set_title(title, fontsize=14, loc="left")
    handles = [Line2D([0], [0], color=CATEGORY_COLORS_5[c], lw=3, label=c) for c in CATEGORY_ORDER_5]
    ax.legend(handles=handles, title=f"HVI kategorisi ({year})", loc="lower right", frameon=True, fontsize=9)
    fig.text(0.01, 0.01, "Veri: Landsat (USGS), © OpenStreetMap katkıcıları (ODbL), Meta & CIESIN HRSL (CC BY 4.0), "
             "TÜİK / belediye açık verisi. Önceliklendirme aracıdır, sağlık verisiyle doğrulanmamıştır.",
             fontsize=6.5, color="#555555")
    _scale_bar(ax)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png", bbox_inches="tight")
    plt.close(fig)


def _scale_bar(ax) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span = x1 - x0
    length = 10 ** np.floor(np.log10(span / 4))
    if span / length > 8:
        length *= 2
    x, y = x0 + span * 0.04, y0 + (y1 - y0) * 0.05
    ax.plot([x, x + length], [y, y], color="black", lw=2)
    ax.text(x + length / 2, y + (y1 - y0) * 0.012, f"{length / 1000:g} km", ha="center", fontsize=8)


def _plot_top_mahalle(mahalle: pd.DataFrame, year: str, path: Path, count: int = 15) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = mahalle[mahalle["guvenilir_ortalama"] == "Evet"].head(count).iloc[::-1]
    if top.empty:
        return
    labels = [f"{r.mahalle_adi} ({r.ilce_adi})" for _, r in top.iterrows()]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(top) + 1.4), dpi=150)
    bars = ax.barh(labels, top[f"hvi_ort_{year}"], color="#de2d26")
    has_prob = "olasilik_ilk_20" in top
    for bar, (_, row) in zip(bars, top.iterrows(), strict=True):
        text = f"{row[f'hvi_ort_{year}']:.1f}"
        if has_prob and pd.notna(row["olasilik_ilk_20"]):
            text += f"   ilk 20: %{row['olasilik_ilk_20'] * 100:.0f}"
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, text, va="center", fontsize=8)
    ax.set_xlim(0, 135 if has_prob else 110)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel(f"Ortalama HVI ({year}, 0-100)")
    title = f"En yüksek ortalama ısı riskli {len(top)} mahalle"
    if has_prob:
        title += "\n\"ilk 20\": belirsizlik analizinde ilk 20 mahalle arasında kalma olasılığı"
    ax.set_title(title, loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png")
    plt.close(fig)


def _plot_groups(mahalle_roads: pd.DataFrame, mahalle: pd.DataFrame, year: str, path: Path, count: int = 15) -> None:
    """En riskli mahallelerde üç grubun ortalama skoru: riskin sıcaktan mı, kalabalıktan mı geldiği."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = [(f"grup_tehlike_{year}", "Tehlike", "#e6550d"), (f"grup_maruziyet_{year}", "Maruziyet", "#756bb1"),
              (f"grup_kirilganlik_{year}", "Kırılganlık", "#31a354")]
    groups = [g for g in groups if g[0] in mahalle_roads]
    top = mahalle[mahalle["guvenilir_ortalama"] == "Evet"].head(count)
    if top.empty or not groups:
        return
    means = mahalle_roads.groupby(["mahalle_adi", "ilce_adi"])[[g[0] for g in groups]].mean()
    keys = list(zip(top["mahalle_adi"], top["ilce_adi"], strict=True))[::-1]
    values = means.reindex(keys)
    labels = [f"{m} ({i})" for m, i in keys]
    y = np.arange(len(keys))
    height = 0.8 / len(groups)
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(keys) + 1.4), dpi=150)
    for k, (column, label, color) in enumerate(groups):
        ax.barh(y + (k - (len(groups) - 1) / 2) * height, values[column], height=height, label=label, color=color)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Ortalama grup skoru (0-1, şehrin kendi dağılımına göre)")
    ax.set_title("En riskli mahallelerde risk nereden geliyor?", loc="left")
    ax.legend(loc="lower right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png")
    plt.close(fig)


def _plot_categories(roads: pd.DataFrame, years: list[str], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.arange(len(CATEGORY_ORDER_5))
    width = 0.8 / len(years)
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    shades = ["#9e9ac8", "#54278f", "#3f007d", "#bcbddc"]
    for k, year in enumerate(years):
        counts = roads[f"hvi_kategori_{year}"].value_counts().reindex(CATEGORY_ORDER_5, fill_value=0)
        km = [roads.loc[roads[f"hvi_kategori_{year}"] == c, "uzunluk_m"].sum() / 1000 for c in CATEGORY_ORDER_5]
        ax.bar(x + (k - (len(years) - 1) / 2) * width, km, width=width, label=year, color=shades[k % len(shades)])
        del counts
    ax.set_xticks(x, CATEGORY_ORDER_5)
    ax.set_ylabel("Yol uzunluğu (km)")
    ax.set_title("HVI kategorilerine göre yol uzunluğu", loc="left")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    with atomic_output_path(path) as temporary:
        fig.savefig(temporary, format="png")
    plt.close(fig)


def _report_html(config: CityConfig, years: list[str], summary: list[tuple[str, str]], mahalle: pd.DataFrame,
                 images: list[tuple[str, str]], files: list[tuple[str, str, str]]) -> str:
    main = years[-1]
    top = mahalle[mahalle["guvenilir_ortalama"] == "Evet"].head(10)
    has_prob = "olasilik_ilk_20" in top
    rows = "".join(
        f"<tr><td>{int(r.sira)}</td><td>{escape(str(r.mahalle_adi))}</td><td>{escape(str(r.ilce_adi))}</td>"
        f"<td>{r[f'hvi_ort_{main}']:.1f}</td><td>{r[f'yuksek_risk_payi_{main}'] * 100:.0f}%</td>"
        + (f"<td>{r['olasilik_ilk_20'] * 100:.0f}%</td>" if has_prob else "")
        + "</tr>"
        for _, r in top.iterrows()
    )
    prob_head = "<th>İlk 20'de kalma olasılığı</th>" if has_prob else ""
    summary_html = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in summary
                           if k not in ("Önemli uyarı",))
    images_html = "".join(f'<figure><img src="{escape(src)}" alt="{escape(alt)}"><figcaption>{escape(alt)}</figcaption></figure>'
                          for src, alt in images)
    files_html = "".join(f'<li><a href="{escape(href)}">{escape(name)}</a>: {escape(desc)}</li>' for name, href, desc in files)
    sources_html = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>{escape(c)}</td></tr>" for a, b, c in SOURCES)
    citation = citation_text(config.name)
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(config.name)} ısı riski özeti</title>
<style>
:root {{ --ink:#1f1d1a; --muted:#6b645c; --line:#e4ddd3; --accent:#b2381f; --paper:#fffdf9; }}
body {{ font-family: Georgia, 'Iowan Old Style', serif; color:var(--ink); background:var(--paper); max-width:900px;
       margin:0 auto; padding:32px 16px 64px; line-height:1.55; }}
h1 {{ font-size:2rem; margin:0 0 4px; }} h2 {{ font-size:1.2rem; margin-top:2.2em; border-bottom:1px solid var(--line); }}
.lead {{ color:var(--muted); margin-top:0; }}
.warn {{ border-left:4px solid var(--accent); background:#fbefe9; padding:10px 14px; font-size:.95rem; }}
table {{ border-collapse:collapse; width:100%; font-size:.9rem; font-family: system-ui, sans-serif; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }}
figure {{ margin:20px 0; }} img {{ max-width:100%; height:auto; border:1px solid var(--line); }}
figcaption {{ font-size:.85rem; color:var(--muted); }}
code {{ font-size:.85rem; }} a {{ color:var(--accent); }}
@media print {{ body {{ max-width:none; padding:0; }} a {{ color:inherit; }} h2 {{ break-after:avoid; }}
               figure {{ break-inside:avoid; }} }}
</style></head><body>
<h1>{escape(config.name)}: sokak ölçekli ısı riski</h1>
<p class="lead">Isı Hassasiyet Endeksi (HVI) özeti, {escape(', '.join(years))}. Canlı harita:
<a href="{SITE_URL}/{escape(config.city_id)}/">{SITE_URL}/{escape(config.city_id)}/</a></p>
<p class="warn">{escape(DISCLAIMER)}</p>
<h2>Bu nedir?</h2>
<p>Her yol segmentine 0-100 arası bir puan verilir. Puan üç sorunun cevabını birleştirir: burası sıcak mı
(uydudan ölçülen yaz yüzey sıcaklığı), burada çok insan var mı (nüfus ve bina yoğunluğu), buradaki insanlar
kırılgan mı (yaşlı ve çocuk oranı, ilçenin gelişmişliği, ağaç azlığı, sağlık tesisine ve parka uzaklık).
Üç grup birbirini telafi edemez: sıcak olmayan ya da kimsenin yaşamadığı bir yolda risk düşük kalır.</p>
<h2>Özet</h2><table>{summary_html}</table>
<h2>En yüksek ortalama HVI'li mahalleler ({escape(main)})</h2>
<table><tr><th>Sıra</th><th>Mahalle</th><th>İlçe</th><th>Ortalama HVI</th><th>Kritik + Aşırı Kritik yol payı</th>{prob_head}</tr>{rows}</table>
<p style="font-size:.85rem;color:var(--muted)">Yalnızca en az {MIN_SEGMENTS_PER_MAHALLE} yol segmenti olan mahalleler.
Tam liste Excel dosyasının "Mahalleler" sayfasında.</p>
<h2>Görseller</h2>{images_html}
<h2>Dosyalar</h2><ul>{files_html}</ul>
<h2>Kaynaklar ve lisans</h2><table><tr><th>Veri</th><th>Kaynak</th><th>Lisans</th></tr>{sources_html}</table>
<h2>Atıf</h2><p><code>{escape(citation)}</code></p>
<p style="font-size:.85rem;color:var(--muted)">Yöntem, sınırlamalar ve kod: <a href="{REPO_URL}">{REPO_URL}</a></p>
</body></html>
"""


def _load_mahalle_polygons(config: CityConfig) -> gpd.GeoDataFrame | None:
    """Adapter'ın mahalle katmanı (yalnızca geometri ve ad). Ağ ya da veri yoksa paket poligonsuz üretilir."""
    try:
        adapter = load_population_adapter(config)
        loader = getattr(adapter, "load_cached_population_data", None)
        paths = loader(config) if callable(loader) else adapter.fetch_population_data(config)
        layer = adapter.build_neighborhood_layer(resolve_pbf_path(config.city_id), paths, config)
    except Exception as error:  # noqa: BLE001 - poligonlar paketin isteğe bağlı parçası
        print(f"  Mahalle poligonları alınamadı ({type(error).__name__}: {error}); paket poligonsuz üretiliyor")
        return None
    return layer[["mahalle_adi", "ilce_adi", "geometry"]].copy()


def export_city_package(config: CityConfig, roads: gpd.GeoDataFrame | None = None,
                        mahalle_polys: gpd.GeoDataFrame | None = None, include_polygons: bool = True,
                        out_dir: Path | None = None, docs_dir: Path | None = None) -> Path:
    """Şehrin veri paketini üretir ve zip yolunu döndürür (ayrıntı modül docstring'inde)."""
    proc = city_data_proc(config.city_id)
    if roads is None:
        roads = gpd.read_file(proc / "roads_with_hvi.geojson")
    years = detect_years(roads)
    if not years:
        raise ValueError(f"{config.name}: roads_with_hvi.geojson içinde hvi_score_<yıl> sütunu yok")
    main = years[-1]
    out_dir = out_dir or package_dir(config)
    docs_dir = docs_dir or DOCS_DIR / config.city_id / "indir"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    prefix = config.city_id

    uncertainty_dir = proc / "uncertainty"
    uncertainty_summary = None
    uncertainty_roads = None
    uncertainty_mahalle = None
    if (uncertainty_dir / "belirsizlik_ozet.json").exists():
        uncertainty_summary = json.loads((uncertainty_dir / "belirsizlik_ozet.json").read_text(encoding="utf-8"))
        if uncertainty_summary.get("year") != main:
            uncertainty_summary = None
    if uncertainty_summary:
        uncertainty_roads = gpd.read_file(uncertainty_dir / "belirsizlik_yollar.geojson", ignore_geometry=True)
        if (uncertainty_dir / "belirsizlik_mahalleler.csv").exists():
            uncertainty_mahalle = pd.read_csv(uncertainty_dir / "belirsizlik_mahalleler.csv")

    tidy = tidy_roads(roads, years)
    if uncertainty_roads is not None and "yol_no" in uncertainty_roads:
        # `yol_no`, roads_with_hvi.geojson'daki satır sırasıdır (bkz. core/uncertainty.py).
        extra = uncertainty_roads.set_index("yol_no")[["olasilik_ilk_yuzde10", "sira_p05", "sira_p95"]]
        tidy = tidy.join(extra)

    mahalle = area_table(tidy, years, ["mahalle_adi", "ilce_adi"])
    if uncertainty_mahalle is not None:
        split = uncertainty_mahalle["mahalle"].str.extract(r"^(?P<mahalle_adi>.*) \((?P<ilce_adi>[^()]*)\)$")
        extra = pd.concat([split, uncertainty_mahalle[["sira_medyan", "olasilik_ilk_5", "olasilik_ilk_20"]]], axis=1)
        mahalle = mahalle.merge(extra, on=["mahalle_adi", "ilce_adi"], how="left")
    ilce = area_table(tidy, years, ["ilce_adi"])
    priority = priority_roads(tidy, main)
    summary = summary_rows(config, tidy, mahalle, years, uncertainty_summary)

    sheets = {"Özet": pd.DataFrame(summary, columns=["Başlık", "Değer"]), "Mahalleler": mahalle, "İlçeler": ilce,
              "Öncelikli yollar": priority}
    all_columns = list(dict.fromkeys([*mahalle.columns, *ilce.columns, *priority.columns]))
    sheets["Sütun sözlüğü"] = column_dictionary(all_columns)
    sheets["Kaynaklar ve lisans"] = pd.DataFrame(SOURCES, columns=["Veri", "Kaynak", "Lisans"])
    write_workbook(out_dir / f"{prefix}_isi_riski.xlsx", sheets)

    for name, frame in (("mahalleler", mahalle), ("ilceler", ilce), ("oncelikli_yollar", priority)):
        frame.to_csv(out_dir / f"{prefix}_{name}.csv", index=False)
    sheets["Sütun sözlüğü"].to_csv(out_dir / "sutun_sozlugu.csv", index=False)
    pd.DataFrame(tidy.drop(columns=tidy.geometry.name)).to_csv(out_dir / f"{prefix}_yollar.csv", index=False)

    if include_polygons and mahalle_polys is None:
        mahalle_polys = _load_mahalle_polygons(config)
    gpkg = out_dir / f"{prefix}_isi_riski.gpkg"
    tidy.to_file(gpkg, layer="yollar", driver="GPKG")
    if mahalle_polys is not None:
        polys = mahalle_polys.dissolve(by=["mahalle_adi", "ilce_adi"], as_index=False)
        polys.merge(mahalle, on=["mahalle_adi", "ilce_adi"], how="inner").to_file(gpkg, layer="mahalleler", driver="GPKG")

    images = [
        ("harita.png", f"{config.name}: yollar HVI kategorisine göre ({main})"),
        ("en_riskli_mahalleler.png", "En yüksek ortalama HVI'li mahalleler"),
        ("risk_kaynagi.png", "En riskli mahallelerde tehlike, maruziyet ve kırılganlık grup skorları"),
        ("kategori_dagilimi.png", "HVI kategorilerine göre yol uzunluğu, yıllara göre"),
    ]
    _plot_map(tidy, mahalle_polys, main, f"{config.name}: sokak ölçekli ısı riski ({main})", out_dir / images[0][0])
    _plot_top_mahalle(mahalle, main, out_dir / images[1][0])
    _plot_groups(tidy, mahalle, main, out_dir / images[2][0])
    _plot_categories(tidy, years, out_dir / images[3][0])
    images = [(src, alt) for src, alt in images if (out_dir / src).exists()]

    zip_name = f"{prefix}_veri_paketi.zip"
    files = [
        (f"{prefix}_isi_riski.xlsx", f"{prefix}_isi_riski.xlsx", "Excel: özet, mahalleler, ilçeler, öncelikli yollar, sözlük"),
        (f"{prefix}_mahalleler.csv", f"{prefix}_mahalleler.csv", "Mahalle tablosu (CSV)"),
        (f"{prefix}_ilceler.csv", f"{prefix}_ilceler.csv", "İlçe tablosu (CSV)"),
        (f"{prefix}_oncelikli_yollar.csv", f"{prefix}_oncelikli_yollar.csv", f"En riskli {PRIORITY_ROAD_COUNT} yol (CSV)"),
        (zip_name, f"{RELEASE_DOWNLOAD_URL}/{zip_name}",
         "Tam paket: tüm yollar (CSV ve GeoPackage), mahalle poligonları, görseller"),
    ]
    html = _report_html(config, years, summary, mahalle, images, files)
    with atomic_output_path(out_dir / "ozet.html") as temporary:
        temporary.write_text(html, encoding="utf-8")
    (out_dir / "OKUBENI.txt").write_text(
        f"{config.name} ısı riski veri paketi\n\nÖnce ozet.html dosyasını açın. Tablolar {prefix}_isi_riski.xlsx "
        f"içinde; CBS için {prefix}_isi_riski.gpkg (yollar ve mahalleler katmanları).\n"
        f"Sütunların anlamı: sutun_sozlugu.csv\n\n{DISCLAIMER}\n\nLisans: ODbL 1.0 (OpenStreetMap türevi). "
        f"Kaynaklar ve atıf: ozet.html\nKod ve yöntem: {REPO_URL}\n",
        encoding="utf-8",
    )
    manifest = DOCS_DIR / config.city_id / "manifest.json"
    if manifest.exists():
        shutil.copy2(manifest, out_dir / "manifest.json")

    zip_path = out_dir.parent / zip_name
    with atomic_output_path(zip_path) as temporary, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out_dir.iterdir()):
            archive.write(path, arcname=f"{prefix}_veri_paketi/{path.name}")

    # Sitede doğrudan sunulan küçük dosyalar. Yol katmanı (CSV, GPKG) zip'te.
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(parents=True)
    for name in [f"{prefix}_isi_riski.xlsx", f"{prefix}_mahalleler.csv", f"{prefix}_ilceler.csv",
                 f"{prefix}_oncelikli_yollar.csv", "ozet.html", *[src for src, _ in images]]:
        shutil.copy2(out_dir / name, docs_dir / name)
    print(f"Veri paketi: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB), site kopyası: {docs_dir}")
    return zip_path
