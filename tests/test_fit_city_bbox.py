import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from tools.fit_city_bbox import _key, _pick_target_ilce, _utm_epsg


@pytest.mark.parametrize(
    ("longitude", "expected"),
    [
        (26.0, "EPSG:32635"),
        (27.1, "EPSG:32635"),
        (30.0, "EPSG:32636"),
        (35.3, "EPSG:32636"),
        (36.0, "EPSG:32637"),
        (44.0, "EPSG:32638"),
    ],
)
def test_utm_epsg_uses_the_correct_turkish_zone(longitude, expected):
    assert _utm_epsg(longitude) == expected


def test_key_normalizes_turkish_names_and_non_text_values():
    assert _key("  İzmir Mahallesi ") == "IZMIR"
    assert _key(None) == ""
    assert _key(float("nan")) == ""


def _admin_frame(rows: list[tuple[str, object]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [name for name, geometry in rows], "geometry": [geometry for name, geometry in rows]},
        crs="EPSG:4326",
    )


def test_pick_target_ilce_resolves_merkez_and_chooses_nearest_duplicate():
    ilce = _admin_frame(
        [
            ("Example Merkez", box(30.0, 40.0, 30.2, 40.2)),
            ("Akyazı", box(30.0, 40.0, 30.2, 40.2)),
            ("Akyazı", box(31.0, 41.0, 31.2, 41.2)),
        ]
    )

    picked, missing = _pick_target_ilce(ilce, ["Merkez", "Akyazı"], "Example", Point(30.05, 40.05))

    assert [row["name"] for row in picked] == ["Example Merkez", "Akyazı"]
    assert missing == []


def test_pick_target_ilce_does_not_match_another_citys_merkez():
    ilce = _admin_frame([("Kilis Merkez", box(36.5, 36.5, 36.7, 36.7))])

    picked, missing = _pick_target_ilce(ilce, ["Merkez"], "Example", Point(30.05, 40.05))

    assert picked == []
    assert missing == ["Merkez"]
