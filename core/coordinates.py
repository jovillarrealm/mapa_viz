import re
from typing import ClassVar, cast

import geopandas as gpd
import pandas as pd

from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result


class CoordinateParser:
    """
    Parser for geographic and projected point coordinates across various formats
    (Decimal Degrees, DMS, DDM, projected metric CRSs like UTM, MAGNA-SIRGAS, Web Mercator).
    """

    # Extended candidate column names for latitude / northing
    LAT_CANDIDATES: ClassVar[list[str]] = [
        "lat",
        "latitude",
        "latitud",
        "lat_dd",
        "decimallatitud",
        "latitud decimal",
        "latitud_decimal",
        "x",
        "latitud (gms)",
        "northing",
        "norte",
        "utmn",
        "utm_n",
        "coord_norte",
        "norte_m",
        "y_coord",
        "north",
    ]

    # Extended candidate column names for longitude / easting
    LON_CANDIDATES: ClassVar[list[str]] = [
        "lon",
        "long",
        "longitude",
        "longitud",
        "lon_dd",
        "decimallongitud",
        "longitud decimal",
        "longitud_decimal",
        "y",
        "lwngitud (gms)",
        "longitud (gms)",
        "easting",
        "este",
        "utme",
        "utm_e",
        "coord_este",
        "este_m",
        "x_coord",
        "east",
    ]

    # DMS regex: 6° 14' 39.1" N or 06d14m39.1s N or 6 14 39.1 N
    _DMS_REGEX: ClassVar[re.Pattern[str]] = re.compile(
        r"""^\s*
        (?P<deg>[-+]?\d+(?:[\.,]\d+)?)      # Degrees
        [\s°d\*:_]*
        (?P<min>\d+(?:[\.,]\d+)?)?         # Minutes
        [\s'm\*:_]*
        (?P<sec>\d+(?:[\.,]\d+)?)?         # Seconds
        [\s"s]*
        (?P<dir>[NSEWOSnsewos])?           # Direction (N, S, E, W, O, Norte, Sur, Este, Oeste)
        \s*$""",
        re.VERBOSE,
    )

    # Common CRS name aliases to EPSG mapping
    _CRS_ALIASES: ClassVar[dict[str, str]] = {
        "wgs84": "EPSG:4326",
        "4326": "EPSG:4326",
        "epsg:4326": "EPSG:4326",
        "magna": "EPSG:4686",
        "magna-sirgas": "EPSG:4686",
        "4686": "EPSG:4686",
        "epsg:4686": "EPSG:4686",
        "magna_origen_nacional": "EPSG:9377",
        "ctm12": "EPSG:9377",
        "9377": "EPSG:9377",
        "epsg:9377": "EPSG:9377",
        "magna_bogota": "EPSG:3116",
        "3116": "EPSG:3116",
        "epsg:3116": "EPSG:3116",
        "3114": "EPSG:3114",
        "epsg:3114": "EPSG:3114",
        "3115": "EPSG:3115",
        "epsg:3115": "EPSG:3115",
        "3117": "EPSG:3117",
        "epsg:3117": "EPSG:3117",
        "3118": "EPSG:3118",
        "epsg:3118": "EPSG:3118",
        "web_mercator": "EPSG:3857",
        "3857": "EPSG:3857",
        "epsg:3857": "EPSG:3857",
        "900913": "EPSG:3857",
        "nad83": "EPSG:4269",
        "4269": "EPSG:4269",
        "epsg:4269": "EPSG:4269",
    }

    @classmethod
    def parse_single_coordinate(cls, val: object) -> float | None:
        """
        Parses a single coordinate value into float decimal degrees / meters.
        Supports numbers, numeric strings, comma decimals, DMS, DDM, and directional suffixes.
        """
        if val is None or pd.isna(val):
            return None

        if isinstance(val, (int, float)):
            return float(val)

        val_str = str(val).strip()
        if not val_str:
            return None

        # Try plain float (replace comma with dot if present)
        clean_plain = val_str.replace(",", ".")
        try:
            return float(clean_plain)
        except ValueError:
            pass

        # Check for directional hemisphere suffix/prefix
        direction = None
        match_dir = re.search(r"([NSEWOSnsewos]|Norte|Sur|Este|Oeste)\b", val_str, re.IGNORECASE)
        if match_dir:
            direction = match_dir.group(1).upper()[0]

        # Extract numeric components
        match_dms = cls._DMS_REGEX.match(val_str)
        if match_dms:
            groups = match_dms.groupdict()
            try:
                deg = float(groups["deg"].replace(",", ".")) if groups["deg"] else 0.0
                minutes = float(groups["min"].replace(",", ".")) if groups["min"] else 0.0
                sec = float(groups["sec"].replace(",", ".")) if groups["sec"] else 0.0

                dir_char = groups["dir"].upper()[0] if groups["dir"] else direction

                sign = -1.0 if deg < 0 else 1.0
                abs_deg = abs(deg)
                decimal_val = sign * (abs_deg + (minutes / 60.0) + (sec / 3600.0))

                if dir_char in ("S", "W", "O"):
                    decimal_val = -abs(decimal_val)
                elif dir_char in ("N", "E"):
                    decimal_val = abs(decimal_val)

                return decimal_val
            except Exception:
                pass

        # Fallback: extract all float numbers found in string
        numbers = [float(n.replace(",", ".")) for n in re.findall(r"[-+]?\d+(?:[\.,]\d+)?", val_str)]
        if len(numbers) == 1:
            res = numbers[0]
            if direction in ("S", "W", "O"):
                res = -abs(res)
            return res
        elif len(numbers) == 2:  # DDM: degrees minutes
            deg, minutes = numbers
            res = (abs(deg) + (minutes / 60.0)) * (-1.0 if deg < 0 else 1.0)
            if direction in ("S", "W", "O"):
                res = -abs(res)
            return res
        elif len(numbers) >= 3:  # DMS: degrees minutes seconds
            deg, minutes, sec = numbers[:3]
            res = (abs(deg) + (minutes / 60.0) + (sec / 3600.0)) * (-1.0 if deg < 0 else 1.0)
            if direction in ("S", "W", "O"):
                res = -abs(res)
            return res

        return None

    @classmethod
    def parse_coordinate_series(cls, series: pd.Series) -> pd.Series:
        """Vectorized / mapped parsing of a pandas Series into float coordinates."""
        return cast(pd.Series, series.apply(cls.parse_single_coordinate))

    @classmethod
    def normalize_crs(cls, crs_input: str) -> str:
        """
        Normalizes CRS names/aliases into valid EPSG strings (e.g. 'EPSG:4326', 'EPSG:3116', 'EPSG:9377').
        Supports UTM zone descriptions (e.g. 'UTM 18N', 'UTM Zone 18S').
        """
        if not crs_input:
            return "EPSG:4326"

        key = crs_input.strip().lower()
        if key in cls._CRS_ALIASES:
            return cls._CRS_ALIASES[key]

        # Check UTM zone pattern (e.g. UTM 18N, UTM Zone 18S, 18N)
        utm_match = re.match(r"^(?:utm\s*(?:zone)?)?\s*(\d{1,2})\s*([ns])$", key)
        if utm_match:
            zone = int(utm_match.group(1))
            hemisphere = utm_match.group(2)
            if 1 <= zone <= 60:
                code = 32600 + zone if hemisphere == "n" else 32700 + zone
                return f"EPSG:{code}"

        if not key.startswith("epsg:") and key.isdigit():
            return f"EPSG:{key}"

        return crs_input.strip()

    @classmethod
    def infer_projected_crs(cls, x_vals: pd.Series, y_vals: pd.Series) -> str | None:
        """
        Infer common projected CRS when coordinates are metric (outside lat/lon bounds).
        Supported auto-inferences:
        - MAGNA-SIRGAS Origen Nacional (EPSG:9377)
        - MAGNA-SIRGAS Bogota Zone (EPSG:3116)
        - Web Mercator (EPSG:3857)
        """
        valid_x = x_vals.dropna()
        valid_y = y_vals.dropna()

        if len(valid_x) == 0 or len(valid_y) == 0:
            return None

        x_mean = float(valid_x.mean())
        y_mean = float(valid_y.mean())

        # If already geographic lat/lon ([-180, 180] and [-90, 90])
        if (-180 <= x_mean <= 180) and (-90 <= y_mean <= 90):
            return "EPSG:4326"

        # MAGNA-SIRGAS Origen Nacional EPSG:9377 (Easting ~ 5,000,000, Northing ~ 2,000,000)
        if (4_000_000 <= x_mean <= 6_000_000) and (1_000_000 <= y_mean <= 3_000_000):
            return "EPSG:9377"

        # MAGNA-SIRGAS Bogota Zone EPSG:3116 (Easting ~ 1,000,000, Northing ~ 1,000,000)
        if (700_000 <= x_mean <= 1_300_000) and (700_000 <= y_mean <= 1_500_000):
            return "EPSG:3116"

        # Web Mercator EPSG:3857 (X in millions, Y in millions)
        if abs(x_mean) > 1_000_000 and abs(x_mean) <= 20_000_000 and abs(y_mean) <= 20_000_000:
            return "EPSG:3857"

        return None


def prepare_spatial_dataframe(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    source_crs: str = "EPSG:4326",
) -> Result[tuple[gpd.GeoDataFrame, str], SpatialError]:
    """
    Cleans coordinate columns, handles projected CRSs (UTM, MAGNA-SIRGAS, Web Mercator),
    reprojects to EPSG:4326 WGS84, and updates lat/lon columns to WGS84 decimal degrees.
    Returns Result[(GeoDataFrame, effective_crs_string), SpatialError].
    """
    clean_df = df.copy()

    # Parse numeric / string coordinates into float values
    parsed_lat = CoordinateParser.parse_coordinate_series(clean_df[lat_col])
    parsed_lon = CoordinateParser.parse_coordinate_series(clean_df[lon_col])

    clean_df[lat_col] = parsed_lat
    clean_df[lon_col] = parsed_lon

    valid_df = clean_df.dropna(subset=[lat_col, lon_col]).copy()
    if len(valid_df) == 0:
        return Err(
            SpatialError(
                code=SpatialErrorCode.EmptyDataset,
                message="No valid coordinate rows remaining after coordinate parsing",
            )
        )

    norm_crs = CoordinateParser.normalize_crs(source_crs)

    # If source CRS was set to default EPSG:4326, but coordinates are projected metric values,
    # attempt automatic projected CRS inference.
    if norm_crs == "EPSG:4326":
        inferred = CoordinateParser.infer_projected_crs(valid_df[lon_col], valid_df[lat_col])
        if inferred and inferred != "EPSG:4326":
            norm_crs = inferred

    try:
        geometry = gpd.points_from_xy(valid_df[lon_col], valid_df[lat_col])
        gdf = gpd.GeoDataFrame(valid_df, geometry=geometry, crs=norm_crs)

        # Reproject to WGS84 EPSG:4326 if in another projected CRS
        if gdf.crs and str(gdf.crs).upper() != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
            # Update lat/lon columns to reflect reprojected WGS84 decimal degrees
            gdf[lat_col] = gdf.geometry.y
            gdf[lon_col] = gdf.geometry.x

        return Ok((gdf, str(gdf.crs)))
    except Exception as e:
        return Err(
            SpatialError(
                code=SpatialErrorCode.InvalidCRS,
                message=f"Failed to create or reproject spatial dataframe with CRS '{norm_crs}': {e}",
                details=str(e),
            )
        )
