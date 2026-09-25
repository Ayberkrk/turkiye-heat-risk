import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, box

from core.coverage import road_coverage

CRS = "EPSG:32636"


def _mahalle(values: list[float | None]) -> gpd.GeoDataFrame:
    """Yan yana iki kare mahalle (batıda A, doğuda B); `values` her birinin
    demografi değeri (None = NaN, yani CSV'de olmayan ilçe)."""
    boxes = [box(30.60, 36.80, 30.70, 36.90), box(30.70, 36.80, 30.80, 36.90)]
    data = {"geometry": boxes[: len(values)]}
    for col in ("nufus_yogunlugu", "yasli_oran", "cocuk_oran"):
        data[col] = [np.nan if v is None else v for v in values]
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


def _roads(*xs: float) -> gpd.GeoDataFrame:
    """Her x (boylam) için o noktada küçük bir yol."""
    return gpd.GeoDataFrame(
        geometry=[LineString([(x, 36.84), (x + 0.001, 36.84)]) for x in xs], crs="EPSG:4326"
    )


def test_coverage_is_share_of_roads_in_mahalle_with_demography():
    # 3 yol batı mahallede (demografisi var), 1 yol doğu mahallede (NaN).
    mahalle = _mahalle([100.0, None])
    roads = _roads(30.62, 30.64, 30.66, 30.75)

    assert road_coverage(mahalle, roads, CRS) == 0.75


def test_coverage_is_zero_when_every_mahalle_lacks_demography():
    # Adapter'ın ilçe adı OSM'dekiyle eşleşmediğinde görülen durum: her şey NaN.
    assert road_coverage(_mahalle([None, None]), _roads(30.62, 30.75), CRS) == 0.0


def test_coverage_is_zero_without_roads_or_mahalle():
    assert road_coverage(_mahalle([100.0, 100.0]), _roads(), CRS) == 0.0
    assert road_coverage(_mahalle([]), _roads(30.62), CRS) == 0.0


def test_road_outside_every_mahalle_counts_as_uncovered():
    assert road_coverage(_mahalle([100.0, 100.0]), _roads(30.62, 30.95), CRS) == 0.5


def test_sosyoekonomik_skor_must_also_be_present_when_the_column_exists():
    mahalle = _mahalle([100.0, 100.0])
    mahalle["sosyoekonomik_skor"] = [1.0, np.nan]

    assert road_coverage(mahalle, _roads(30.62, 30.75), CRS) == 0.5
