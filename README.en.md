# Urban Heat Island and Heat Vulnerability Index (HVI)

[![Tests](https://github.com/Ayberkrk/turkiye-heat-risk/actions/workflows/tests.yml/badge.svg)](https://github.com/Ayberkrk/turkiye-heat-risk/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![version](https://img.shields.io/github/v/tag/Ayberkrk/turkiye-heat-risk?label=version&color=informational)](https://github.com/Ayberkrk/turkiye-heat-risk/releases)
[![good first issues](https://img.shields.io/github/issues/Ayberkrk/turkiye-heat-risk/good%20first%20issue?label=good%20first%20issues&color=7057ff)](https://github.com/Ayberkrk/turkiye-heat-risk/labels/good%20first%20issue)

See [CHANGELOG.md](CHANGELOG.md) for the release history and
[CITATION.cff](CITATION.cff) for citation.

> The Turkish original of this document: [README.md](README.md).

## English summary

An open-data, reproducible urban heat risk pipeline. It combines Landsat
land surface temperature (LST), the OpenStreetMap road network, and
demographic data into a street-level, explainable Heat Vulnerability Index
(HVI): Landsat LST/NDVI, a road-to-temperature spatial join, and an index
that groups nine components into Hazard (surface temperature), Exposure
(population and built-up density) and Vulnerability (elderly/child share,
socioeconomic development, distance to health care and green space, tree
canopy). Components are averaged within a group and the three groups are
combined by geometric mean, so each group carries one third of the index
regardless of how many components it holds. Categories use Jenks natural
breaks shared across years. Live maps:
<https://ayberkrk.github.io/turkiye-heat-risk/>. The index is a
prioritisation tool; it has not been validated against health outcomes. The architecture is city-agnostic -
`src/core/` never changes when a new city is added; 70 cities are supported
today (Izmir, Eskişehir, Şanlıurfa, Antalya, Mersin, Adana and 64 more, listed
with their data sources and measured OSM coverage in
[the register](docs/turkiye-ilce-yas-verisi-taramasi.md); see
[CONTRIBUTING.md](CONTRIBUTING.md) to add another). Cities that cover a single
district have constant demographic components, so their maps show heat and
green cover, not demographic vulnerability.

Quick start (produces a single-file interactive HTML map):

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

The rest of this document is the English translation of the Turkish original.
If the two disagree, [README.md](README.md) is the reference.

---

An open-data, reproducible urban heat risk analysis pipeline. It combines
Landsat land surface temperature, the OpenStreetMap road network and
demographic data to map heat risk at street scale. It has a city-agnostic
architecture; 70 cities are supported today (İzmir, Eskişehir, Şanlıurfa,
Antalya, Mersin, Adana and 64 more cities; their sources and their coverage
measured against real OSM are on the [register
page](docs/turkiye-ilce-yas-verisi-taramasi.md)).
Adding a new city is possible without changing any file in `src/core/`
(see [CONTRIBUTING.md](CONTRIBUTING.md)).

**Live map:** <https://ayberkrk.github.io/turkiye-heat-risk/> (a small version
hosted on GitHub Pages that loads data on demand; its source is in `docs/`).
The fully offline, single-file version (~60 MB; not kept in the repository
because it exceeds GitHub's 50 MB warning / 100 MB rejection limit) is produced
locally in a few minutes with the command below:

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

![İzmir HVI interactive map: the road network coloured from orange to dark red by the Heat Vulnerability Index, with the layer control at top right and the year selector and legend at bottom left](assets/screenshots/harita-genel.png)

## Table of contents

- [What does it do?](#what-does-it-do)
- [Adapting to another city/region](#adapting-to-another-cityregion)
- [Methodology](#methodology)
- [Multi-year sensitivity and intervention analysis](#multi-year-sensitivity-and-intervention-analysis)
- [2020 → 2026: Findings](#2020--2026-findings)
- [Setup and running](#setup-and-running)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)

## What does it do?

1. **Satellite data** - downloads the least cloudy summer scenes covering the
   İzmir metropolitan area from Landsat 8/9 (Microsoft Planetary Computer).
2. **Land surface temperature (LST) and NDVI** - computes the true surface
   temperature (°C) from the thermal band and vegetation density from the
   red/near-infrared bands; merges the scenes into a single seamless mosaic.
3. **Road network ↔ temperature join** - assigns to each of the ~44,000 road
   segments pulled from OpenStreetMap the mean LST within a 10-metre buffer and
   converts it to a 0-100 "risk score".
4. **Heat Vulnerability Index (HVI)** - combines temperature, tree cover,
   population density, elderly/child population share, distance to
   hospital/pharmacy, distance to green space and built-up density into a single
   0-100 score; it answers the question "this place is both hot and
   crowded/elderly/child-heavy and also treeless and far from health care, so
   the real risk is here". Each component's own value is stored separately
   too - the final score is visible not on its own but together with the
   factors that make it up (see Methodology).
5. **Interactive map** - produces a Folium/Leaflet map that opens as a single
   file in the browser, with category-based toggleable layers, a 2020/2026 year
   selector and a tooltip that shows every component making up the score when a
   road is clicked.
6. **Multi-year analysis package (optional)** - compares three or more years
   against the ERA5-Land air anomaly; measures ranking stability by changing the
   HVI weights and road buffers; shows afforestation and shading what-if
   scenarios on a separate map.

## Adapting to another city/region

The project now has a per-city architecture: the code under `src/core/` is
entirely city-agnostic; everything specific to İzmir is isolated in
`src/cities/izmir/config.yaml` and `src/cities/izmir/adapter.py`. Adding a new
city does **not** require changing the constants in `src/core/` - for the
step-by-step process see [CONTRIBUTING.md](CONTRIBUTING.md). In short
(`<city>` below stands for the city identifier you choose):

**1. Create `src/cities/<city>/config.yaml`**
Here you write `bbox` (as [west, south, east, north] in degrees), the target
UTM `crs`, the OSM `.osm.pbf` extract URL
([openstreetmap.fr](https://download.openstreetmap.fr/extracts/) or
[Geofabrik](https://download.geofabrik.de/)), and `admin_level_ilce` /
`admin_level_mahalle` (the OSM admin levels for district and neighbourhood;
they change from country to country - check yours beforehand with
`osm_gdf['admin_level'].unique()`).

**2. Write a demographic "adapter" (the most labour-intensive step)**
Two reference examples show different data source scenarios:
  - `src/cities/izmir/adapter.py`: neighbourhood-level population/age if the
    municipality has its own CKAN-based open data portal
    (`acikveri.bizizmir.com`).
  - `src/cities/eskisehir/adapter.py`: the template for when such a portal does
    NOT exist, using TÜİK's publicly available district-level ADNKS releases as
    static CSV - it can be adapted for almost any other Turkish city without its
    own CKAN with next to no changes. The shared logic is in
    `src/core/ilce_table_adapter.py`. When adding a new city, verify the
    district-level 0-14, 15-64 and 65+ counts for the same year; do not write
    provincial shares into a district row as a fallback. Some older city records
    in the repository use provincial shares; these are also flagged on the
    register page. `tools/fit_city_bbox.py` derives the bbox from the dense
    neighbourhood cluster and measures the HVI coverage against real OSM
    (threshold 60%, see `validate_city.py --osm-coverage`). The central district
    may be written as "<Province> Merkez" in OSM and "Merkez" in the CSV (or the
    other way round); `core/ilce_table_adapter.py` maps this.

Both examples implement the `fetch_population_data()` /
`build_neighborhood_layer()` interface. Write your own adapter implementing the
same interface under `src/cities/<city>/adapter.py` for a new city:
  - You can keep fetching neighbourhood/administrative boundary polygons from
    OSM.
  - Get the population density, elderly population share and child population
    share data as CSV/JSON from the national statistics office (TÜİK, Eurostat,
    US Census, etc.) or from the municipality's own open data portal.
  - The neighbourhood-district mapping is done in both adapters **by spatial
    query, not by name** (`sjoin`, whether the centroid falls inside) - this
    prevents same-named neighbourhoods from being matched with the wrong
    district. Keep this approach; it works whatever country you are in.

**3. Validate and run**
```bash
python validate_city.py <city>
python pipeline.py --city <city> --years <years>
```
`validate_city.py` checks before downloading that config.yaml contains the
required fields, that the bbox is valid, that the adapter can be imported and
that the data source URLs are reachable.

**4. Change the HVI components**
`COMPONENT_GROUPS` in `src/core/hvi.py` defines which component goes into which
group (hazard, exposure, vulnerability). To add a new component, produce its
column with `robust_normalize_0_1`, add it to the relevant group and increment
`HVI_FORMULA_VERSION`.

## Methodology

### Land surface temperature (LST)

Landsat Collection 2 Level-2 products already calibrate the thermal band to
surface temperature in Kelvin in the laboratory. All that is needed is the scale
conversion:

```
LST(K) = pixel_value × 0.00341802 + 149.0
LST(°C) = LST(K) - 273.15
```

Scenes are searched by default between 1 July and 31 August. Since the hot
season changes from city to city, the window can be adjusted in the `landsat`
section of `config.yaml` (`season_start: "06-15"`, `season_end: "09-15"`). The
same window must be used when comparing across years; after changing the window,
have the scenes re-selected with `--force`.

**The thermal band's true resolution is 100 m.** The Landsat 8/9 TIRS sensor
measures surface temperature at about 100 m; the USGS product resamples it to a
30 m grid. So although the temperature on the map is reported per road segment,
streets closer than 100 m to each other largely share the same measurement: the
map distinguishes hot areas within a neighbourhood, not individual neighbouring
streets. NDVI (30 m) does not carry this limitation.

Because clouds corrupt the infrared, the cloud cover is kept below 30% while
searching each scene, and up to `max_scenes_per_tile` (default 3, set in the
`landsat` section of `config.yaml`) dates are selected for each satellite tile
(path/row).

A low scene-level cloud cover alone is not enough: even in a scene with a low
total cloud cover, a small part of the cloud may fall directly over the study
area. So the `QA_PIXEL` band is also downloaded and, before LST and NDVI are
computed, a pixel-level cloud mask is applied on the scene's own pixel grid
(before mosaicking and reprojection): pixels carrying any of the fill, dilated
cloud, cirrus, cloud, cloud shadow and snow flags are made `NaN`/nodata
(`core/raster.py`, `qa_invalid_mask`).

**Multi-scene composite:** instead of selecting a single scene, the LST/NDVI of
the `max_scenes_per_tile` scenes selected for each tile are computed separately
(with the QA mask applied on each one's own grid) and their pixel-wise **median**
is taken (`core/raster.py`, `composite_scene_arrays`). Since scenes of the same
tile from different dates do not come on the same pixel grid (the origin can
shift by hundreds of metres), the scenes are first fitted to the tile's common
grid (`tile_grid`) and then the median is taken. The median is more robust than
the mean - it prevents a single outlier cloudy/abnormal day from dominating the
result. This reduces the single-scene noise mentioned in the "Methodological
caveat" below (the same approach was already used for the night heat island
layer in `core/night_lst.py`). With `max_scenes_per_tile: 1` the old
single-scene behaviour can be restored.

**Cities on a UTM zone boundary:** USGS projects each Landsat scene into the UTM
zone closest to its centre. If a city's bbox happens to fall at a point where
two neighbouring path/row tiles intersect and these tiles fall into different
UTM zones (this happened in Eskişehir: 3 of 4 tiles in UTM 36N/EPSG:32636, one
in UTM 35N/EPSG:32635), all scenes are reprojected to `config.crs` before
mosaicking (`core/raster.py`, `reproject_to_crs`) - otherwise `stream_mosaic`
pastes the scene from the different zone in the wrong place (because the same
numerical coordinates correspond to a different geographic location) and almost
no valid pixels remain in that area.

### Road ↔ temperature join (spatial join)

Since roads are line geometries, a pixel average cannot be taken directly; each
road is given a 10-metre buffer and the **mean** of the pixels falling inside
this corridor (against outliers `mean` is more robust than `max`) is computed
with `rasterstats.zonal_stats`. The result is converted into a "risk score" by
normalising it to 0-100 according to the common min-max range of all roads.

### Heat Vulnerability Index (HVI): multi-component and explainable

The HVI collects nine components into three groups and combines the groups with
the geometric mean:

```
Group score = arithmetic mean of the group's components
HVI         = geometric_mean(Hazard, Exposure, Vulnerability) × 100
```

| Group | Component | What it measures | Source |
|---|---|---|---|
| Hazard | Surface temperature | LST risk score (per year) | Landsat thermal band |
| Exposure | Population density | People/km² | City adapter (municipal open data or TÜİK) |
| Exposure | Built-up density | Building density within 150 m of the road | OSM building (`building`) layer |
| Vulnerability | Elderly share | 65+ population share (district) | City adapter |
| Vulnerability | Child share | 0-14 population share (district) | City adapter |
| Vulnerability | Socioeconomic development | Inverse of the district-level SEGE-2022 score | T.C. Ministry of Industry and Technology, official SEGE-2022 report |
| Vulnerability | Health access | Distance to the nearest hospital/clinic/pharmacy | OSM (`amenity=hospital/clinic/pharmacy`) |
| Vulnerability | Green space access | Distance to the nearest park/forest/meadow polygon | OSM (`leisure=park`, `landuse=forest` etc.) |
| Vulnerability | Tree cover | Inverse of the mean NDVI in the road buffer | Landsat NDVI |

**Why grouped?** In v1.x the plain geometric mean of the nine components was
taken. There the number of components was a hidden weight: a single temperature
component against seven vulnerability components pushed temperature's share in a
*heat* index down to 1/9. Also, components related to each other (NDVI with LST,
buildings with population density) counted the same signal twice. In the grouped
structure each group's share is 1/3 regardless of how many components it holds.
This gives the same ranking as the Hazard × Exposure × Vulnerability framework in
the disaster risk literature (the geometric mean of the three groups is the cube
root of their product).

**Within-group and between-group difference:** components in the same group can
compensate for one another (a road with a low elderly share but poor health
access comes out at medium vulnerability), so the arithmetic mean is used within
a group. The groups, however, cannot compensate for one another: however high
the vulnerability on a road that is not hot or where nobody lives, the risk must
stay low, so the geometric mean is used between groups.

**Group scores are rescaled before being combined.** Taking a mean narrows the
spread: in the six-component vulnerability group the components cancel each
other out (elderly and child shares are inversely related) and the group score
stays in a narrow band. A group stuck in a narrow band does not affect the
ranking even if its weight is 1/3; in İzmir, without this step, vulnerability's
rank correlation with the HVI came out at 0.00. So all three group scores are
pulled to 0-1 according to the common distribution of all years, and then
combined. This step does not equalise the effects (see the measurement in
"Findings") but it prevents any group from staying decorative.

**Scaling is robust to outliers:** each component is pulled to 0-1 according to
the 2%-98% percentile range instead of min-max, and values outside are clipped to
0 or 1. With min-max a single extreme road (e.g. a rural segment 40 km from the
nearest hospital) squeezed all the remaining roads into a narrow band of the
scale.

**Components that do not discriminate are not included in the index:** if a
component takes the same value on all of a city's roads (district-level
demographic components in single-district cities) it does not enter the group
mean; otherwise a constant 0 would dilute the effect of the group's other
members. In this case the pipeline prints which components it left out.

The geometric mean has a side effect: 0 means "the lowest value in the dataset",
not "no risk at all", and on its own it zeroes the whole score. So group scores
are scaled to the range `[0.05, 1]` before being combined. This preserves the
behaviour "if one group is low, the total risk is low too", but a single group
score cannot take over completely.

**These choices are a judgement, not a measurement.** The equal group shares and
which group the components fall into are not calibrated against health outcomes.
`analyze_pipeline.py` reports how much the ranking changes with different weight
profiles (see "Multi-year sensitivity and intervention analysis"); the index
itself has not yet been validated against hospital admissions or mortality data
(see "Known limitations").

**The two years are comparable:** the HVI percentage and the Jenks category
breaks are computed from the **common** distribution of all years, not separately
for each year. If each year were scaled to 0-100 within itself, by definition
each year's worst road would come out at 100% and it would be impossible to say
"risk increased in 2026". The common-scale logic applied to the LST risk score is
carried on in the HVI too.

**Labels by percentile:** labels on the map such as "high / medium / very close"
are produced according to rank (percentile), not equal-width intervals. With
equal intervals a few extreme values took over the whole scale and 91% of roads
came out "very close to the hospital"; now each label corresponds to roughly a
fifth of the roads.

**Explainability:** alongside the final HVI score, each component's own
normalised value and the three group scores are written to the GeoJSON
(`hazard_norm_<year>`, `exposure_norm`, `sensitivity_*_norm`, `group_*_<year>`
columns) and turned into readable labels in the map tooltip such as
"Temperature: high, Tree cover: very low, Distance to hospital: far..." - why a
road's HVI is high/low can be seen directly on the map.

Since age distribution data exists only at **district** level, a district's
elderly/child share is applied to all of that district's neighbourhoods in the
same way (downscaling) - it misses fine within-district differences, but it is a
standard and honest approach when working with coarse data.

**Socioeconomic component:** no current, reliable education/income indicator at
neighbourhood/district level could be found in the İzmir Metropolitan
Municipality open data portal or at TÜİK; instead the district-level development
score from the T.C. Ministry of Industry and Technology's official **"Research on
the Socio-Economic Development Ranking of Districts (SEGE-2022)"** report was
used - a publicly available, one-off official study covering all the districts of
the 81 provinces with 56 variables (demography, employment, education, health,
finance, competitiveness, quality of life). That is why, instead of being
downloaded from CKAN, it was included in the repository as a small reference
file, `src/cities/izmir/sege_2022_ilce.csv` (see `cities/izmir/adapter.py`). This
component is **optional** - if another city's adapter does not provide this data,
the HVI continues to be computed with the remaining components.

**This HVI is not a comprehensive health or socioeconomic vulnerability model;
it is a multi-component prioritisation index built from the available open
data.**

### Categorisation: why Jenks natural breaks?

Because the HVI scores are the geometric mean of three group scores, the
distribution is skewed - most roads pile up at low scores and a few roads jump
to very high scores. The first attempt used `pd.qcut` (an equal number of roads
in each category), but that reflected a forcibly equal division, not the real
structure in the data. **Jenks natural breaks** (`jenkspy`) instead finds
mathematically the breaks that minimise within-group variance and maximise
between-group variance - that is, it detects the clustering points "that exist in
nature", rather than forcibly distributing an equal number of roads into
categories. The Jenks breaks are computed once from the **common** distribution
of the two years, not separately for 2020 and 2026; so "Critical" means the same
threshold in both years and a road changing category between years shows a real
change.

(This is a separate decision from the component labels such as "high / very
close" in the tooltip: **categories** are produced with Jenks, **labels** with
percentiles. With categories the aim is to find the real clustering in the data;
with labels, to give the reader the answer to the question "where does this road
stand relative to the others".)

### Time series: why are 2020 vs 2026 normalised "commonly"?

If you normalise the risk score with each year's own min-max, "45°C in 2020" and
"45°C in 2026" correspond to different scores - the comparison becomes
meaningless. Instead the LST values of the two years are combined and **a single
common min-max range** is found; both years are measured with this same ruler.

### Night heat island (optional, `--night-lst`)

Landsat's thermal band is designed for the daytime overpass; the night heat
island effect (city centres cooling more slowly at night than the countryside, an
effect generally felt more strongly than in the day) was not in this data set.
The `--night-lst` flag fetches MODIS's "LST_Night_1km" product from the same
Planetary Computer infrastructure (the pixel-wise mean of all its 8-day summer
composites, to prevent a single cloudy night from dominating the result). Because
MODIS is at 1 km resolution (unlike Landsat's 30 m), this layer is presented at
**neighbourhood** scale rather than per road segment and is not included in the
HVI score - it is a separate layer on the map, off by default.

## Multi-year sensitivity and intervention analysis

The main pipeline's map can compare two or more years. For a longer period,
weather correction and decision scenarios, run the second command after the main
pipeline outputs for at least three years are ready. Example:

```bash
python pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
python analyze_pipeline.py --city izmir --years 2013 2016 2019 2022 2024 2026 --main-year 2026
```

The analysis reads the prepared raster and road/HVI output of the given years; it
does not re-run the satellite download and the main pipeline. Years from 2013
onwards of the Landsat 8/9 archive are usable. The weather source is
[the ERA5-Land reanalysis in Open-Meteo's historical weather
API](https://open-meteo.com/en/docs/historical-weather-api). ERA5-Land provides a
consistent historical temperature series since 1950. 12 sample locations are used
in the study area.

The weather correction subtracts the mean 2 m air temperature of the selected
Landsat scene days from the 1991-2020 normal of the same calendar days within a
±7 day window. This anomaly is subtracted from the road's Landsat LST as
`β × anomaly`. `β` is a hypothetical matching coefficient; the results for
`β=0`, `0.5` and `1` are reported. ERA5-Land air temperature and Landsat surface
temperature are different measurements; the corrected value is a sensitivity
estimate, not an LST value validated against station measurements. The annual
linear trend is a descriptive summary, not a causal climate effect estimate.

The HVI sensitivity table computes the existing components with three explicit
weight profiles: equal, heat-priority and equity-priority. The spatial
sensitivity analysis by default re-samples LST/NDVI in 10, 30 and 50 m road
buffers. For each option, the overlap of the last year's top 10% riskiest road
set with the default profile and the Spearman rank correlation are reported. Thus,
instead of differences arising from different score ranges, which roads remain in
the priority list is measured.

The public-health convergence check compares the road-length-weighted LST with the
65+ age share from open data sources at district level. The number of districts
and the Pearson/Spearman relationships are in `heat_health_convergence.csv`. Since
the age share is an HVI component this is not an independent accuracy test; it is
an overlap check of the raw heat map with the distribution of the age group that
is sensitive from a health point of view. Because there is no neighbourhood-level
age data, the result makes no claim beyond the district scale.

Scenarios are applied to the default top 20% of road segments in the last year's
equal-weight HVI ranking. The initial assumptions are NDVI `+0.15` in the tree
scenario, LST `-2°C` in the shading scenario and both in the combined scenario.
They can be changed with `--target-share`, `--ndvi-delta` and `--cooling-c`. In
addition to the mean HVI change, the output gives the 65+ share, the population
density and the share in the top 65+ quintile of the targeted roads. This what-if
calculation is not a measured tree/shade effect, a cost or a health outcome.

The analysis products are written under
`data/processed/<city>/impact_analysis/`: `annual_weather_adjusted.csv`,
`robustness.csv`, `heat_health_convergence.csv`, `intervention_scenarios.csv`,
`impact_scenarios.geojson`, `analysis_summary.json` and `analysis_map.html`.
Because the GeoJSON is large, the map is viewed not via a file URL but by
starting a local HTTP server in this folder:

```bash
cd data/processed/izmir/impact_analysis
python -m http.server 8000
```

Then open `http://localhost:8000/analysis_map.html`.

## 2020 → 2026: Findings

*(İzmir, a 6-year window. For each year, the pixel-wise median of 4 satellite
tiles with 3 July-August Landsat scenes per tile, 12 in total. The numbers come
from the same data set that also feeds the map:
`data/processed/izmir/roads_timeseries.geojson` and
`roads_with_hvi.geojson`. Which scenes were used is in
`docs/izmir/manifest.json`.)*

**Temperature - overall trend:**
- The mean surface temperature of 44,041 road segments was 42.6 °C in 2020 and
  43.1 °C in 2026: mean change **+0.47 °C**.
- Most-warmed road: **+13.5 °C** · most-cooled road: **-7.6 °C**
- **49%** of roads warmed (by more than +0.5 °C), **23%** cooled, **27%**
  practically did not change. Only 1.6% warmed by +3 °C or more.

> **About the "+3.29 °C" figure in earlier versions:** the v1.x README said a
> mean warming of +3.29 °C and "98% of roads warmed". Those numbers were produced
> from a **single** scene per tile and reflected the weather difference between
> the days selected for the two years. With the median of three scenes of the
> same tile the difference falls to +0.47 °C. The lesson: a year-over-year
> warming conclusion cannot be drawn from a single satellite overpass.

**HVI - risk distribution (grouped methodology, 5 categories, with the two
years' common Jenks breaks; 43,183 roads with matched demographics):**

| Category | 2020 | 2026 | Change |
|---|---|---|---|
| Low | 7,462 | 5,659 | -1,803 |
| Medium | 11,902 | 12,091 | +189 |
| High | 9,569 | 10,739 | +1,170 |
| Critical | 9,694 | 9,799 | +105 |
| Extreme Critical | 4,556 | 4,895 | +339 |

Because the category breaks are computed once from the two years' common
distribution, "Critical" means the same threshold in both years. The shift is
mainly at the lower end: roads leaving the Low category moved to Medium and High;
the Critical and Extreme Critical total **increased by 3%** (from 14,250 to
14,694). Since the demographic and OSM components are the same in both years, all
of this change comes from temperature and vegetation.

> Note: these numbers cannot be compared with those in v1.x. In v2.0.0 the index
> moved to a grouped structure, the scaling changed and the temperature input
> comes from a median composite instead of a single scene.

**The 5 neighbourhoods with the highest mean HVI (2026, among the 418
neighbourhoods with at least 20 road segments):**

1. Umut Mahallesi (Karabağlar) - 90.4%
2. Sarıyer Mahallesi (Karabağlar) - 89.7%
3. Uğur Mumcu Mahallesi (Karabağlar) - 89.4%
4. İhsan Alyanak Mahallesi (Karabağlar) - 88.5%
5. Bozyaka Mahallesi (Karabağlar) - 86.4%

At district-average level Karabağlar (70.5%) is far ahead; then come Buca (56.2%),
Bayraklı (55.3%) and Karşıyaka (53.7%). The top of the list is largely the same
neighbourhoods as in v1.x: the result is stable against the formula change.

**The groups' real effect on the index (2026, rank correlation between the group
score and the HVI):** exposure 0.82 · hazard 0.39 · vulnerability 0.23. Although
the three groups have equal weight, their effects are not equal: in İzmir the
spatial distribution of risk is determined most of all by population and built-up
density. In other words this map highlights mainly places that are "hot AND
crowded"; because the vulnerability components are at district level,
within-neighbourhood discrimination is weak.

**What can be done?**
- The 14,694 road segments in the Critical/Extreme Critical category (~34% of the
  scored roads) can be prioritised for interventions such as afforestation,
  shading, light-coloured surfaces.
- A road's HVI can be read from the map tooltip together with the "why" question -
  e.g. if a road is both hot and treeless and far from a hospital, this points at
  the same time to three separate types of intervention (shading, health access
  planning, emergency preparedness).
- Continuing the monitoring is recommended - future years can be added easily
  with the `--years` parameter.

**Methodological caveat:** +0.47 °C is the surface temperature difference between
the two years' summer median composites and should not be interpreted as a
long-term climate trend. Two points do not establish a trend; the median
composite reduces single-day anomalies but does not remove that summer's general
weather conditions (hot/cool summer, soil moisture). For a multi-year estimate
cleaned of weather conditions, `analyze_pipeline.py` can be used.

## Setup and running

```bash
git clone <this-repo>
cd turkiye-heat-risk
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The version ranges in `requirements.txt` are upper-bounded against major-version
breaks but are still ranges; to reproduce exactly the environment that works
today (GDAL-based packages such as `rasterio`/`geopandas` can change behaviour
even in a minor version), install with the pinned versions in `constraints.txt`:

```bash
pip install -r requirements.txt -c constraints.txt
```

To run the whole pipeline (download → LST/NDVI → road join → HVI → map):

```bash
python pipeline.py --city izmir --years 2020 2026 --main-year 2026 --open
```

- `--city`: the city id in `src/cities/<city>/config.yaml` (default: `izmir`)
- `--years`: the years to compare (can be 2 or more)
- `--main-year`: which year uses the "main/plain" folder structure
  (`data/raw/<city>/...` vs. `data/raw/<city>/<year>/...`)
- `--open`: open automatically in the browser after the map is produced
- `--force`: ignore the road risk score and HVI cache, recompute
- `--night-lst`: also produce the MODIS night heat island layer at neighbourhood
  scale (optional, downloads an additional satellite source - see Methodology)

Every step is skipped if its output is already on disk - even if the script is
interrupted halfway, `python pipeline.py --city izmir` continues from where it
left off. The first run (4 Landsat scenes × 2 years + OSM extract) takes ~15-25
minutes and ~5-6 GB of disk space on a reasonable internet connection.

The road risk score and HVI outputs are recomputed automatically when the formula
version changes (see `src/core/cache.py`); if the data source stays the same and
you only want to try parameters, it can be forced by hand with `--force`.

For the multi-year analysis package, give the years in the example above to the
main pipeline, then adjust the weather coefficient, buffer and intervention
assumptions with `analyze_pipeline.py --help`. ERA5-Land needs an internet
connection on the first run; the daily series is cached per city. The analysis
jobs run sequentially and do not process large rasters concurrently.

## Tests

Unit tests for pure/logic-heavy functions (normalisation, percentile labelling,
config validation, cache validity) are under `tests/` - they need no satellite
download or OSM network and run in seconds:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

`.github/workflows/tests.yml` runs the same suite automatically on every push and
PR - if a contribution (e.g. a new city adapter) breaks the tests, it is visible
before merge.

## Running with Docker

Installing `rasterio`/GDAL can be troublesome from machine to machine (especially
on Windows) - the `Dockerfile` gives the guarantee "if this image works, it works
on your machine too". The outputs (`data/`, `output/`, `docs/`) are mounted to the
host so that they persist outside the container:

```bash
docker build -t turkiye-heat-risk .
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/docs:/app/docs" \
  turkiye-heat-risk --city izmir --years 2020 2026 --main-year 2026
```

`.github/workflows/tests.yml` automatically verifies on every push/PR that the
image really builds and the module installs soundly (with a light smoke test,
without running the heavy/network-dependent full pipeline).

## Hosting (GitHub Pages)

`pipeline.py` produces two maps for each city (see `core/map_builder.py`):
`output/<city>_hvi_map.html` (single file, offline) and `docs/<city>/` (data split
into separate small GeoJSON files, the browser downloads only the layer that is
opened - first page load a few hundred KB). To publish the second one:

1. Run `python pipeline.py --city <city>` for at least one city.
2. Produce the cross-city comparison page (`docs/index.html`) with
   `python build_docs_index.py`.
3. Commit the `docs/` folder, and in GitHub choose Settings → Pages → Branch:
   `main`, folder: `/docs`.

This repository's own page: <https://ayberkrk.github.io/turkiye-heat-risk/>

## Reproducibility: the map manifest

Next to both map outputs (`output/<city>_hvi_map.html` and
`docs/<city>/index.html`), a small JSON file is also written recording the
inputs/settings they were produced with:
`output/<city>_hvi_manifest.json` and `docs/<city>/manifest.json` respectively
(see `core/map_builder.py`, `_build_manifest`). Its contents:

- city id/name, production time (UTC)
- the requested years and the main year
- the relevant fields of the city config (bbox, CRS, cloud cover/scene-count-per-
  tile limit, road buffer, OSM admin_levels, pbf URL)
- for each year, the identity/date/tile/cloud cover of the Landsat scenes used
  (from `scene_metadata.json`, see `core/satellite.py`)
- formula/cache version numbers (`HVI_FORMULA_VERSION`,
  `RISK_TIMESERIES_VERSION`, `MOSAIC_VERSION`, `SCENE_FETCH_VERSION`)
- whether the night heat island layer (`--night-lst`) was requested

Raw rasters, large intermediate outputs such as the full `roads_with_hvi.geojson`,
or credentials (none are stored anyway) are NOT written to the manifest - only
small, descriptive metadata. To inspect it:

```bash
python -m json.tool docs/izmir/manifest.json
```

## Project structure

```
turkiye-heat-risk/
├── pipeline.py               # Single top-level entry point: python pipeline.py --city izmir
├── analyze_pipeline.py       # Multi-year weather/sensitivity/what-if analysis package
├── validate_city.py           # Quickly validates a new city's config.yaml
├── build_docs_index.py        # Produces the comparison page for the cities under docs/
├── src/
│   ├── core/                  # City-agnostic, general pipeline logic
│   │   ├── city_config.py     #   config.yaml loader + validation
│   │   ├── satellite.py       #   Landsat download
│   │   ├── raster.py          #   LST/NDVI computation + memory-safe mosaicking
│   │   ├── roads.py           #   OSM road network + annual temperature/NDVI join
│   │   ├── impact_analysis.py #   weather correction, HVI sensitivity and intervention scenarios
│   │   ├── osm_amenities.py   #   health/green space/building layers (from OSM)
│   │   ├── hvi.py             #   multi-component HVI computation
│   │   ├── map_builder.py     #   interactive Folium map (offline + hosting version)
│   │   ├── night_lst.py       #   optional: neighbourhood-scale MODIS night heat island layer
│   │   ├── cache.py           #   version-stamped cache validity for intermediate outputs
│   │   ├── ilce_table_adapter.py #  shared neighbourhood-layer logic for TÜİK-templated cities (2 CSV -> neighbourhood)
│   │   └── text_utils.py      #   Turkish text normalisation shared across cities
│   └── cities/
│       ├── izmir/
│       │   ├── config.yaml         #   İzmir-specific bbox, URLs, column mappings
│       │   ├── adapter.py          #   İzmir-specific population/demography logic (CKAN)
│       │   └── sege_2022_ilce.csv  #   District-level socioeconomic development score (official SEGE-2022)
│       ├── eskisehir/
│       │   ├── config.yaml         #   Eskişehir-specific bbox, URLs
│       │   ├── adapter.py          #   TÜİK-based population/demography logic (template without CKAN)
│       │   ├── ilce_nufus.csv      #   District population + elderly/child share (TÜİK ADNKS 2025)
│       │   └── sege_2022_ilce.csv  #   District-level socioeconomic development score (official SEGE-2022)
│       └── sanliurfa/, antalya/, mersin/, adana/  # Same TÜİK-based template as Eskişehir
│           ├── config.yaml         #   city-specific bbox/CRS/OSM region extract
│           ├── adapter.py          #   thin wrapper (calls core/ilce_table_adapter.py)
│           ├── ilce_nufus.csv      #   district population + provincial-level elderly/child (0-14) share
│           └── sege_2022_ilce.csv  #   district SEGE-2022 scores (from the official PDF)
├── tests/                     # Unit tests for pure/logic functions (need no network)
├── docs/                      # Small/fetch-based map version served by GitHub Pages
│   ├── index.html             #   cross-city comparison page (produced by build_docs_index.py)
│   └── <city>/                #   index.html + GeoJSON data files + manifest.json (see Reproducibility)
├── output/                    # produced by pipeline.py, not included in git
│   ├── <city>_hvi_map.html  #   fully offline, single-file map (can be opened by double-clicking)
│   └── <city>_hvi_manifest.json  #   record of the inputs/settings that produced that map
├── data/                      # produced by pipeline.py, not included in git
│   ├── raw/<city>/           #   downloaded Landsat bands, OSM extract, population CSVs (separated per city)
│   └── processed/<city>/     #   LST/NDVI mosaics, intermediate GeoJSONs (separated per city)
├── CONTRIBUTING.md            # Steps to add a new city
├── requirements.txt
├── requirements-dev.txt       # Test dependencies (pytest)
├── Dockerfile / .dockerignore # Single-command reproducible working environment
├── LICENSE                    # MIT
└── README.md
```

## Known limitations

- **Cloud cover**: for a tile, up to `max_scenes_per_tile` candidate scenes from
  more than one date are tried (see Methodology) but in some years NO summer scene
  with under 30% cloud may be found over İzmir; in this case `max_cloud_cover` can
  be relaxed but the result quality drops.
- **Age data resolution**: the elderly population share is at district level - the
  real within-neighbourhood distribution may be more variable than this.
- **Single daytime snapshot**: the road-level LST reflects the temperature at the
  time the scene was taken (for Landsat, generally close to the afternoon). The
  night heat island effect (known to be generally stronger) can be added as a
  separate layer with the `--night-lst` flag (MODIS, 1 km resolution), but this
  layer is at neighbourhood rather than road scale and is not included in the HVI
  score - see `core/night_lst.py` and the Methodology section above.
- **Unvalidated index**: the HVI has not been compared with emergency admissions,
  ambulance calls or mortality data during heatwaves. The group shares and the
  choice of components are a judgement based on the framework in the literature.
  The map answers the question "where should we look first"; it does not measure
  how many times more dangerous one road is than another.
- **Surface temperature is not air temperature**: LST is the temperature of the
  surface the satellite sees (roof, asphalt, treetop); the air temperature a
  pedestrian feels, humidity, wind and shade are different from this. A street
  whose treetops look cool may be shaded at pedestrian level; a narrow street
  whose roofs look hot may stay in shade at pedestrian level.
- **Thermal resolution 100 m**: although the temperature is reported per road,
  neighbouring streets mostly share the same thermal measurement (see
  Methodology).
- **Cross-city comparison**: components are scaled according to each city's own
  distribution. A road that comes out "Extreme Critical" in one city is among that
  city's riskiest roads; it does not mean that it carries the same absolute risk
  as another city's "Extreme Critical" road.
- **10-metre road buffer**: this narrow buffer used in temperature and NDVI
  sampling may mix in the effect of a neighbouring road on very narrow streets, and
  on very wide boulevards it may not cover the whole corridor. The sensitivity
  package also measures 30 and 50 m alternatives; it does not by itself determine
  which buffer matches ground truth.
- **Scale of the weather correction**: ERA5-Land's roughly 11 km air temperature
  does not measure a 30 m Landsat surface temperature. The correction coefficient
  (`β`) is an assumption and must be compared separately; the analysis is not a
  substitute for local weather stations.
- **Scenario assumptions**: the NDVI increase and LST decrease are user input.
  Tree species, canopy development time, shade geometry, water demand,
  implementation cost or exposure behaviour are not modelled. The difference on
  the map is assumed HVI arithmetic, not an expected health effect.
- **150-metre built-up buffer**: this radius chosen for building density is a
  reasonable urban fabric scale but is a single choice; because the buffers of
  neighbouring roads overlap, nearby roads get a similar density value, so this
  component discriminates at neighbourhood rather than road scale.
- **The SEGE table was transcribed by hand**: the scores in `sege_2022_ilce.csv`
  were extracted by hand from the official report; all 30 districts were compared
  row by row with the T.C. Ministry of Industry and Technology's official
  SEGE-2022 report and verified. Even so, when the report is updated this file
  must be re-checked by hand.
- **Socioeconomic component at district level**: the SEGE-2022 score too (like the
  elderly/child share) is at district level - the real within-neighbourhood
  distribution may be more variable than this. It is also a one-off study dated
  2022; if an updated SEGE report is published in the future,
  `sege_2022_ilce.csv` should be updated.
- **Single-district cities**: 54 of the 70 cities cover a single district; in these
  cities the population density, elderly/child share and SEGE components take the
  same value in all neighbourhoods, do not discriminate the HVI and are not
  included in the index. The map reflects only the LST, NDVI, built-up and access
  components. Also, in Ağrı, Iğdır, Kırklareli and Karaman, because the district
  counts deviate from the provincial level too implausibly, the provincial-level
  0-14/65+ shares are used.
- **A further step of coarser resolution in the TÜİK-templated main cities
  (Eskişehir, Şanlıurfa, Antalya, Mersin, Adana)**: unlike İzmir's
  neighbourhood-level CKAN population data, these adapters could not find a
  district-level TÜİK release for the elderly/child share and therefore apply the
  PROVINCE's overall age distribution (0-14 and 65+) to all districts in the same
  way; population density too is constant at district rather than neighbourhood
  level (because the district area is computed from the OSM administrative
  boundary, density comes out low in districts with a wide rural hinterland).
  Real within-district/within-neighbourhood inequality is therefore less visible
  than in İzmir (see `core/ilce_table_adapter.py` and each city's `adapter.py`
  docstring).

## License

MIT. See [LICENSE](LICENSE).
