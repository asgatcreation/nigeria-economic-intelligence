"""Tests for the COD-AB boundary connector.

The fixture archive is built here rather than committed as a binary,
because what matters is its *shape* -- 37 features, lowercase property
names, Polygon and MultiPolygon mixed, areas that reconcile -- and a
constructed archive states that shape in readable code. Nothing in this
module touches the network: every test passes an explicit path, which
`fetch_archive` returns unchanged.
"""

import json
import zipfile

import pytest

from nigeria_economic_intelligence.ingestion import validate_dataframe
from nigeria_economic_intelligence.sources import cod_ab_boundaries as cod_ab


def _square(lon: float, lat: float, size: float = 0.5):
    return [[
        [lon, lat],
        [lon + size, lat],
        [lon + size, lat + size],
        [lon, lat + size],
        [lon, lat],
    ]]


def _feature(number: int, *, multi: bool = False, **overrides):
    pcode = f"NG{number:03d}"
    # Areas sum to the published national figure by construction, so a
    # test that changes one can rely on the reconciliation check firing.
    properties = {
        "adm1_name": f"State {number}",
        "adm1_pcode": pcode,
        "adm0_name": "Nigeria",
        "area_sqkm": cod_ab.NATIONAL_AREA_SQKM / 37,
        "center_lat": 4.0 + number * 0.2,
        "center_lon": 3.0 + number * 0.2,
    }
    properties.update(overrides)

    if multi:
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [_square(3.0 + number, 4.0),
                            _square(3.0 + number, 6.0)],
        }
    else:
        geometry = {
            "type": "Polygon",
            "coordinates": _square(3.0 + number, 4.0),
        }

    return {"type": "Feature", "properties": properties, "geometry": geometry}


def _archive(tmp_path, features=None, member=cod_ab.ADMIN1_MEMBER):
    if features is None:
        features = [
            _feature(number, multi=number in (3, 9))
            for number in range(1, 38)
        ]

    path = tmp_path / "nga_admin_boundaries.geojson.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(
            member,
            json.dumps({"type": "FeatureCollection", "features": features}),
        )
    return path


def test_loads_all_thirty_seven_states(tmp_path):
    boundaries = cod_ab.load_admin1(_archive(tmp_path))

    assert len(boundaries) == 37
    assert len({boundary.pcode for boundary in boundaries}) == 37
    assert [b.pcode for b in boundaries] == sorted(b.pcode for b in boundaries)


def test_multipolygon_states_keep_every_part(tmp_path):
    boundaries = {
        boundary.pcode: boundary
        for boundary in cod_ab.load_admin1(_archive(tmp_path))
    }

    assert len(boundaries["NG003"].polygons) == 2
    assert len(boundaries["NG001"].polygons) == 1


def test_published_centroids_are_used_not_recomputed(tmp_path):
    """The file supplies centres; deriving our own would add assumptions."""
    boundaries = {
        boundary.pcode: boundary
        for boundary in cod_ab.load_admin1(_archive(tmp_path))
    }

    assert boundaries["NG005"].centre == (4.0 + 5 * 0.2, 3.0 + 5 * 0.2)


def test_refuses_a_file_with_the_wrong_number_of_states(tmp_path):
    features = [_feature(number) for number in range(1, 37)]

    with pytest.raises(RuntimeError, match="Expected 37 states"):
        cod_ab.load_admin1(_archive(tmp_path, features))


def test_refuses_a_feature_without_a_pcode(tmp_path):
    features = [_feature(number) for number in range(1, 38)]
    features[4]["properties"]["adm1_pcode"] = ""

    with pytest.raises(RuntimeError, match="no P-code or name"):
        cod_ab.load_admin1(_archive(tmp_path, features))


def test_refuses_a_feature_without_an_area(tmp_path):
    features = [_feature(number) for number in range(1, 38)]
    features[2]["properties"]["area_sqkm"] = None

    with pytest.raises(RuntimeError, match="has no area_sqkm"):
        cod_ab.load_admin1(_archive(tmp_path, features))


def test_refuses_when_areas_do_not_reconcile(tmp_path):
    """A boundary file for the wrong country would pass every other check."""
    features = [
        _feature(number, area_sqkm=cod_ab.NATIONAL_AREA_SQKM / 37 * 0.5)
        for number in range(1, 38)
    ]

    with pytest.raises(RuntimeError, match="outside the .* tolerance"):
        cod_ab.load_admin1(_archive(tmp_path, features))


def test_accepts_the_real_shortfall_in_generalised_areas(tmp_path):
    """The published file is about 1.5% light; that must not be rejected."""
    features = [
        _feature(number, area_sqkm=cod_ab.NATIONAL_AREA_SQKM / 37 * 0.985)
        for number in range(1, 38)
    ]

    boundaries = cod_ab.load_admin1(_archive(tmp_path, features))

    assert len(boundaries) == 37


def test_refuses_an_archive_without_the_admin1_layer(tmp_path):
    path = _archive(tmp_path, member="nga_admin2.geojson")

    with pytest.raises(RuntimeError, match="has no nga_admin1.geojson"):
        cod_ab.load_admin1(path)


def test_refuses_an_unsupported_geometry(tmp_path):
    features = [_feature(number) for number in range(1, 38)]
    features[7]["geometry"] = {"type": "Point", "coordinates": [3.0, 4.0]}

    with pytest.raises(RuntimeError, match="Unsupported boundary geometry"):
        cod_ab.load_admin1(_archive(tmp_path, features))


def test_fetch_archive_refuses_a_path_that_does_not_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        cod_ab.fetch_archive(tmp_path / "absent.zip")


def test_digest_is_stable_and_hex(tmp_path):
    path = _archive(tmp_path)

    digest = cod_ab.archive_digest(path)

    assert len(digest) == 64
    assert digest == cod_ab.archive_digest(path)


def test_only_areas_are_offered_for_ingestion(tmp_path):
    """Geometry is deliberately not an observation."""
    frame = cod_ab.build_dataframe(_archive(tmp_path))

    assert set(frame["indicator_code"]) == {cod_ab.AREA_INDICATOR}
    assert len(frame) == 37
    assert set(frame["domain"]) == {"geography"}
    assert set(frame["geo_level"]) == {"state"}


def test_output_passes_ingestion_validation(tmp_path):
    frame = cod_ab.build_dataframe(_archive(tmp_path))

    assert len(validate_dataframe(frame)) == 37


def test_areas_are_observed_not_estimated(tmp_path):
    """A published polygon area is a measurement, not a projection."""
    frame = cod_ab.build_dataframe(_archive(tmp_path))

    assert set(frame["observation_status"]) == {"observed"}
