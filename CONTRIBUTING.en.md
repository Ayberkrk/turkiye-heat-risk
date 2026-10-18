# Contributing: Adding a New City

> The Turkish original of this document: [CONTRIBUTING.md](CONTRIBUTING.md).

This project has a per-city architecture: the code under `src/core/` is
entirely city-agnostic, each city's own parameters and population data
logic are isolated under `src/cities/<city>/`. Adding a new city should
not require changing any file in `src/core/`.

## Steps

### 1. Create the `src/cities/<city>/` directory

```bash
mkdir -p src/cities/<city>
touch src/cities/<city>/__init__.py
```

`<city>` should be a short identifier in lower case without Turkish
characters (e.g. `ankara`, `antalya`) - this identifier is used in the
`--city <city>` flag and in the `src/cities/<city>/config.yaml` path.

### 2. Fill in `config.yaml`

Take `src/cities/izmir/config.yaml` as an example. Required fields:

```yaml
city:
  name: "The City's Display Name"
  bbox: [west, south, east, north]   # in degrees
  crs: "EPSG:xxxxx"                   # the UTM zone the city is in (a CRS in metres) -
                                       # do not copy another city's, compute it from longitude:
                                       # UTM zone = floor((longitude + 180) / 6) + 1, EPSG = 32600 + zone (northern hemisphere)

landsat:
  max_cloud_cover: 30                 # % - relax if necessary
  season_start: "07-01"               # optional, "MM-DD" - the start of the hot season
  season_end: "08-31"                 # optional - all years use the same window

osm:
  pbf_url: "https://download.geofabrik.de/... or https://download.openstreetmap.fr/..."
  admin_level_ilce: <number>            # OSM admin_level - varies from country to country
  admin_level_mahalle: <number>
  highway_types: [...]                # which road types to include in the analysis

roads:
  buffer_meters: 10

population:
  adapter: "cities.<city>.adapter"    # step 3 below
  # You can add here the extra keys your adapter needs
  # (CKAN dataset IDs, file paths, API keys, etc.)
```

To verify the `admin_level_ilce` (district) / `admin_level_mahalle`
(neighbourhood) values in advance:

```python
import geopandas as gpd
gdf = gpd.read_file("<pbf-file>", layer="multipolygons", bbox=(west, south, east, north))
print(sorted(gdf[gdf["boundary"] == "administrative"]["admin_level"].dropna().unique()))
```

### 3. Specify the population/demography data source and write the adapter

`src/core/hvi.py` reads the population density, the elderly share and the
child share from `mahalle_gdf` (the neighbourhood GeoDataFrame). Because
this data comes in very different forms from city to city (CKAN, TÜİK,
Eurostat, a national statistics office API...) no general schema is
forced; instead each city writes its own **adapter**.

`src/cities/<city>/adapter.py` must implement these two functions:

```python
def fetch_population_data(config: CityConfig) -> dict[str, Path]:
    """Downloads the population/demography sources (skips if already
    downloaded) and returns the local file paths."""

def build_neighborhood_layer(pbf_path: Path, population_paths: dict[str, Path],
                              config: CityConfig) -> gpd.GeoDataFrame:
    """Enriches the neighbourhood boundaries with population data. The
    returned GeoDataFrame must contain at least these columns:
      - mahalle_adi (neighbourhood name), ilce_adi (district name), geometry
      - nufus_yogunlugu   (population density, people/km²)
      - yasli_oran        (a fraction between 0 and 1, the 65+ population share)
      - cocuk_oran        (a fraction between 0 and 1, the 0-14 population share)

    Optional: if you also add a `sosyoekonomik_skor` (socioeconomic score)
    column (higher = more developed/less vulnerable), the HVI automatically
    uses it as a ninth component - `src/core/hvi.py` checks whether this
    column exists, and the pipeline runs without error even if you do not
    add it.
    """
```

Two reference examples exist, for different data source shapes:

- `src/cities/izmir/adapter.py`: pulling CSV from the municipality's own
  CKAN open data portal (neighbourhood-level population/age), Turkish
  character normalisation, spatial (not by-name) neighbourhood-district
  matching, and embedding an official report (SEGE-2022) in the repository
  as a small reference CSV.
- `src/cities/eskisehir/adapter.py`: the template to use when there is NO
  municipality-specific portal - it uses TÜİK ADNKS district age counts
  (İŞKUR provincial activity reports or TÜİK tables) as static CSV. When
  adding a new city, verify the district-level 0-14, 15-64 and 65+ counts
  for the same year; do not use provincial-level age shares instead of
  district data. If the required district counts cannot be found, do not
  add the city. There are records in the repository that were added before
  this rule and use provincial-level shares; do not replicate these old
  exceptions in new contributions. State the data year and source in the
  adapter and the config attribution.
  This template can be adapted for ANY Turkish city without its own CKAN
  portal with almost no changes - the shared logic is in
  `src/core/ilce_table_adapter.py`, and that city's adapter only provides
  its own `ilce_nufus.csv` and `sege_2022_ilce.csv` paths (Şanlıurfa,
  Antalya, Mersin and Adana were added this way; the shortest example is
  `src/cities/adana/`). Note: this approach fixes the population density
  and the elderly/child share at district level (it cannot capture
  within-neighbourhood variation) - if a more finely grained source such
  as CKAN is available, İzmir's method should be preferred.

**Things to watch out for when adding a TÜİK-templated city (from mistakes
that were made):**
- For `ilce_nufus.csv`, check that the sum of the district populations
  comes out equal to the official provincial total (a source whose total
  does not add up is wrong).
- `YASLI_ORAN` / `COCUK_ORAN` in `ilce_nufus.csv` must be a **fraction
  between 0 and 1** and the child share must be computed with the **0-14**
  age definition. The "child population share" in news reports is generally
  TÜİK's 0-17 definition (in Şanlıurfa 43.3% vs the real 0-14 36.8%) - do
  not use it. For each target district take the same year's 0-14 / 15-64 /
  65+ counts and total population from the source table; verify that the sum
  of the three age groups equals the district total.
- Take the SEGE-2022 scores from the official report, not from secondary
  sources (the PDF at baka.gov.tr; Annex-1 and the provincial tables). The
  text can be extracted with `pypdf`; the decimal separator is a comma
  (`3,173` = 3.173).
- Do not write the bbox by hand, and do not take it from the exact
  administrative boundary either: `tools/fit_city_bbox.py` derives it from
  the district's small/dense (<3 km²) neighbourhood cluster and measures the
  result against real OSM (coverage below). Put the regional extracts in a
  directory named `<region>.osm.pbf` and run
  `python tools/fit_city_bbox.py <city> --pbf-dir <directory> [--apply]`.
- **Coverage** = how many of the roads in the bbox fall into a
  neighbourhood with matched demographics. CSV integrity tests cannot
  measure this; only real OSM boundaries show it.
  `python validate_city.py <city> --osm-coverage` requires at least 60%.
  Traps found: in OSM the central district is written "<Province> Merkez",
  in the table "Merkez" (the adapter maps this); the neighbourhood
  boundaries in OSM sometimes do not cover half the city in small cities; a
  fixed coordinate square (0.2 degrees) often lands in the wrong place
  (Kilis was landing on Gaziantep, not Kilis).
- **In single-district cities** the population density, the elderly/child
  share and the SEGE components are all a constant (a single value) and do
  not contribute to the HVI ranking; the HVI effectively consists of
  temperature, tree cover, health/green space access and built-up density.
  State this in the city's adapter and, if possible, build a multi-district
  core by adding neighbouring districts' data too.
- `KADEME` (tier) in `sege_2022_ilce.csv` must match the score thresholds
  in the report (a test verifies this).
- Do NOT use `curl -C -` (resume) when downloading the OSM extract: if the
  `-latest` file on the server is updated, a broken file is created from
  half of the old + the new part; verify the size with Content-Length.

If you have a different data source shape (e.g. GeoJSON, a direct API) it
is enough to match the signature of these two functions - nothing specific
to CKAN or TÜİK is required.

Raw/processed data (`data/raw/<city>/`, `data/processed/<city>/`) is
separated automatically by city id - you do not need to do anything about
this in your adapter, `src/core/paths.py` handles it for you.

### 4. Run the validation script

```bash
python validate_city.py <city>
python validate_city.py <city> --osm-coverage --pbf <region>.osm.pbf   # coverage against real OSM
```

Without downloading/processing any data this checks the following (except
`--osm-coverage`, which needs a downloaded OSM extract):
- that `config.yaml` contains all the required fields
- that `bbox` is a valid coordinate range
- that the adapter module can be imported and implements both functions
- that the OSM pbf URL and (if any) the CKAN-based population source are
  really reachable
- (with `--osm-coverage`) that a sufficient share of the roads in the bbox
  falls into a neighbourhood with matched demographics

If there are errors the script lists them and exits with code 1.

### 5. Run end to end

```bash
python pipeline.py --city <city> --years <year1> <year2>
```

The first run downloads the Landsat scenes and the OSM extract - depending
on the internet connection it may take 15-25 minutes and several GB of disk
space. If the script is interrupted it continues from where it left off
with the same command.

### 6. Open a pull request

Move your changes to a branch, and when opening the PR state:
- Which city was added, what the bbox and the data source are
- That `validate_city.py <city>` and `pipeline.py --city <city>` completed
  successfully (a short excerpt from the logs is enough)
- The licence/terms of use of the population data (open data portal, TÜİK,
  etc.)

## Requesting a new city (without writing code)

If you do not want to contribute yourself but want a city added, open an
issue with the "Yeni şehir talebi" (New city request) template under
`.github/ISSUE_TEMPLATE/`.

## Code of conduct

This project adopts the [Contributor Covenant](CODE_OF_CONDUCT.md) code of
conduct. By contributing you agree to abide by it.
