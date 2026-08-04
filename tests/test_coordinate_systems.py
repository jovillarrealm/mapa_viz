import pandas as pd
import pytest
from shapely.geometry import Point

from core.adapters import CSVDataAdapter, ExcelDataAdapter
from core.coordinates import CoordinateParser, prepare_spatial_dataframe
from core.result import Ok


def test_dms_and_ddm_parsing():
    # DMS formats
    lat_dms = CoordinateParser.parse_single_coordinate("6° 14' 39.1\" N")
    lon_dms = CoordinateParser.parse_single_coordinate("75° 34' 52.3\" W")
    assert lat_dms is not None and pytest.approx(lat_dms, 1e-4) == 6.244194
    assert lon_dms is not None and pytest.approx(lon_dms, 1e-4) == -75.581194

    # Spanish direction (Sur / Oeste)
    lat_south = CoordinateParser.parse_single_coordinate("06° 14' 39.1\" S")
    lon_oeste = CoordinateParser.parse_single_coordinate("75° 34' 52.3\" O")
    assert lat_south is not None and lat_south < 0
    assert lon_oeste is not None and lon_oeste < 0

    # DDM format
    lat_ddm = CoordinateParser.parse_single_coordinate("6° 14.651' N")
    lon_ddm = CoordinateParser.parse_single_coordinate("75° 34.871' W")
    assert lat_ddm is not None and pytest.approx(lat_ddm, 1e-4) == 6.244183
    assert lon_ddm is not None and pytest.approx(lon_ddm, 1e-4) == -75.581183

    # Comma decimal
    val_comma = CoordinateParser.parse_single_coordinate("-75,5812")
    assert val_comma is not None and pytest.approx(val_comma, 1e-4) == -75.5812


def test_crs_alias_normalization():
    assert CoordinateParser.normalize_crs("UTM 18N") == "EPSG:32618"
    assert CoordinateParser.normalize_crs("UTM Zone 18S") == "EPSG:32718"
    assert CoordinateParser.normalize_crs("MAGNA_ORIGEN_NACIONAL") == "EPSG:9377"
    assert CoordinateParser.normalize_crs("MAGNA_BOGOTA") == "EPSG:3116"
    assert CoordinateParser.normalize_crs("9377") == "EPSG:9377"
    assert CoordinateParser.normalize_crs("4326") == "EPSG:4326"


def test_projected_crs_reprojection_magna():
    # MAGNA-SIRGAS Origen Nacional (EPSG:9377) coordinates for Medellin (~6.244, -75.581)
    # Northing ~ 2,248,000 m, Easting ~ 4,714,000 m
    df = pd.DataFrame(
        {
            "Norte": [2248000.0],
            "Este": [4714000.0],
            "Sitio": ["Medellin"],
        }
    )

    res = prepare_spatial_dataframe(
        df, lat_col="Norte", lon_col="Este", source_crs="EPSG:9377"
    )
    assert isinstance(res, Ok)
    gdf, crs_str = res.value
    assert str(gdf.crs) == "EPSG:4326"
    assert pytest.approx(gdf.geometry.y.iloc[0], 0.1) == 6.24
    assert pytest.approx(gdf.geometry.x.iloc[0], 0.1) == -75.58


def test_projected_crs_reprojection_utm():
    # UTM Zone 18N (EPSG:32618)
    df = pd.DataFrame(
        {
            "Northing": [690000.0],
            "Easting": [435000.0],
            "Sector": ["Sector A"],
        }
    )

    res = prepare_spatial_dataframe(
        df, lat_col="Northing", lon_col="Easting", source_crs="UTM 18N"
    )
    assert isinstance(res, Ok)
    gdf, crs_str = res.value
    assert str(gdf.crs) == "EPSG:4326"
    assert -90 <= gdf.geometry.y.iloc[0] <= 90
    assert -180 <= gdf.geometry.x.iloc[0] <= 180


def test_auto_infer_projected_crs():
    # Metric coordinates without explicit CRS (defaults to EPSG:4326)
    # Magna Origen Nacional range (Easting ~ 4.7M, Northing ~ 2.2M)
    df = pd.DataFrame(
        {
            "y": [2248000.0],
            "x": [4714000.0],
            "Sector": ["Sector B"],
        }
    )

    res = prepare_spatial_dataframe(df, lat_col="y", lon_col="x", source_crs="EPSG:4326")
    assert isinstance(res, Ok)
    gdf, crs_str = res.value
    assert str(gdf.crs) == "EPSG:4326"
    assert pytest.approx(gdf.geometry.y.iloc[0], 0.1) == 6.24
    assert pytest.approx(gdf.geometry.x.iloc[0], 0.1) == -75.58


def test_excel_adapter_with_dms_coordinates():
    df = pd.DataFrame(
        {
            "Latitud (GMS)": ["06°14'39.1\" N", "06°15'10.0\" N"],
            "Longitud (GMS)": ["75°34'52.3\" W", "75°35'00.0\" W"],
            "Sector": ["S1", "S2"],
        }
    )
    adapter = ExcelDataAdapter()
    res = adapter.adapt(df)
    assert isinstance(res, Ok)
    dataset = res.value
    assert dataset.num_points == 2
    assert pytest.approx(dataset.gdf.geometry.y.iloc[0], 1e-3) == 6.244
    assert pytest.approx(dataset.gdf.geometry.x.iloc[0], 1e-3) == -75.581
