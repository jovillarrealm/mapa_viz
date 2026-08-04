import os
from typing import ClassVar

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from core.adapters.base import BaseDataAdapter
from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result


class ExcelDataAdapter(BaseDataAdapter):
    """
    Adapter for Microsoft Excel files (.xlsx, .xls).
    Inspects sheets, auto-detects latitude/longitude columns, validates coordinates,
    maps grouping categories, and builds SpatialDataset wrapped in Result[SpatialDataset, SpatialError].
    """

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
    ]

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
    ]

    GROUP_CANDIDATES: ClassVar[list[str]] = [
        "sector",
        "species cordylancistrus clade tree",
        "species",
        "especie",
        "codigo",
        "code",
        "drainage",
        "cuenca",
        "site",
        "sitio",
        "country",
        "pais",
    ]

    def can_handle(self, source: DataSource) -> bool:
        if isinstance(source, gpd.GeoDataFrame):
            return False
        if isinstance(source, pd.DataFrame):
            return True
        ext = os.path.splitext(os.fspath(source))[1].lower()
        return ext in [".xlsx", ".xls"]

    def _find_best_sheet(self, xl: pd.ExcelFile) -> str:
        """Finds the most likely worksheet containing coordinate data."""
        if len(xl.sheet_names) == 1:
            return xl.sheet_names[0]

        best_sheet = xl.sheet_names[0]
        max_coord_score = -1

        for sheet in xl.sheet_names:
            df_parsed = xl.parse(sheet, nrows=10)
            assert isinstance(df_parsed, pd.DataFrame)
            cols_lower = [str(c).strip().lower() for c in df_parsed.columns]
            score = 0
            for c in cols_lower:
                if c in self.LAT_CANDIDATES:
                    score += 5
                if c in self.LON_CANDIDATES:
                    score += 5
            if score > max_coord_score:
                max_coord_score = score
                best_sheet = sheet

        return best_sheet

    def _detect_lat_lon_columns(
        self, df: pd.DataFrame, lat_col: str | None, lon_col: str | None
    ) -> tuple[str, str] | None:
        cols = [str(c).strip() for c in df.columns]
        col_map = {str(c).strip(): c for c in df.columns}

        # Explicit user specified
        if lat_col and lon_col and lat_col in col_map and lon_col in col_map:
            return col_map[lat_col], col_map[lon_col]

        found_lat = None
        found_lon = None

        # Named candidates search
        for c in cols:
            clower = c.lower()
            if not found_lat and clower in self.LAT_CANDIDATES:
                found_lat = col_map[c]
            if not found_lon and clower in self.LON_CANDIDATES:
                found_lon = col_map[c]

        # Handle 'X' and 'Y' case (e.g. X=Lat, Y=Lon or vice versa)
        if not found_lat or not found_lon:
            x_col = next((col_map[c] for c in cols if c.lower() == "x"), None)
            y_col = next((col_map[c] for c in cols if c.lower() == "y"), None)

            if x_col and y_col:
                x_vals = pd.to_numeric(df[x_col], errors="coerce").dropna()
                y_vals = pd.to_numeric(df[y_col], errors="coerce").dropna()

                if len(x_vals) > 0 and len(y_vals) > 0:
                    if (x_vals.min() >= -15 and x_vals.max() <= 35) and (
                        y_vals.min() <= -30 and y_vals.max() >= -120
                    ):
                        found_lat, found_lon = x_col, y_col
                    elif (y_vals.min() >= -15 and y_vals.max() <= 35) and (
                        x_vals.min() <= -30 and x_vals.max() >= -120
                    ):
                        found_lat, found_lon = y_col, x_col

        # Sanity check lat/lon values
        if found_lat and found_lon:
            lat_vals = pd.to_numeric(df[found_lat], errors="coerce").dropna()
            lon_vals = pd.to_numeric(df[found_lon], errors="coerce").dropna()
            if (
                len(lat_vals) > 0
                and len(lon_vals) > 0
                and lat_vals.mean() < -30
                and lon_vals.mean() > 0
            ):
                found_lat, found_lon = found_lon, found_lat

        if not found_lat or not found_lon:
            return None

        return found_lat, found_lon

    def _detect_group_column(self, df: pd.DataFrame, user_group_col: str | None) -> str:
        cols = [str(c).strip() for c in df.columns]
        col_map = {str(c).strip(): c for c in df.columns}

        if user_group_col and user_group_col in col_map:
            return col_map[user_group_col]

        for c in cols:
            if c.lower() in self.GROUP_CANDIDATES:
                return col_map[c]

        str_cols = df.select_dtypes(include=["object", "category"]).columns
        if len(str_cols) > 0:
            return str_cols[0]

        df["Group"] = "Puntos de Muestreo"
        return "Group"

    def adapt(
        self,
        source: DataSource,
        lat_col: str | None = None,
        lon_col: str | None = None,
        group_col: str | None = None,
        sheet_name: str | None = None,
        crs: str = "EPSG:4326",
        sep: str | None = None,
    ) -> Result[SpatialDataset, SpatialError]:
        if isinstance(source, gpd.GeoDataFrame) or not self.can_handle(source):
            return Err(
                SpatialError(
                    code=SpatialErrorCode.UnsupportedFormat,
                    message=f"Cannot process Excel source '{source}'",
                    source_path=str(source),
                )
            )

        try:
            if isinstance(source, pd.DataFrame):
                source_path = "DataFrame"
                selected_sheet = "InMemoryDataFrame"
                all_sheets = [selected_sheet]
                df = source.copy()
            else:
                source_path = os.fspath(source)
                xl = pd.ExcelFile(source_path)
                selected_sheet = sheet_name or self._find_best_sheet(xl)
                all_sheets = xl.sheet_names
                df_parsed = xl.parse(selected_sheet)
                assert isinstance(df_parsed, pd.DataFrame)
                df = df_parsed

            detected_cols = self._detect_lat_lon_columns(df, lat_col, lon_col)
            if detected_cols is None:
                return Err(
                    SpatialError(
                        code=SpatialErrorCode.MissingCoordinates,
                        message=f"Failed to detect Latitude and Longitude columns in sheet '{selected_sheet}'",
                        source_path=str(source),
                        details=f"Available columns: {list(df.columns)}",
                    )
                )

            resolved_lat, resolved_lon = detected_cols
            resolved_group = self._detect_group_column(df, group_col)

            df[resolved_lat] = pd.to_numeric(df[resolved_lat], errors="coerce")
            df[resolved_lon] = pd.to_numeric(df[resolved_lon], errors="coerce")
            valid_df = df.dropna(subset=[resolved_lat, resolved_lon]).copy()

            if len(valid_df) == 0:
                return Err(
                    SpatialError(
                        code=SpatialErrorCode.EmptyDataset,
                        message="No valid coordinate rows remaining after parsing",
                        source_path=str(source),
                    )
                )

            geometry = [
                Point(xy)
                for xy in zip(
                    valid_df[resolved_lon], valid_df[resolved_lat], strict=False
                )
            ]
            gdf = gpd.GeoDataFrame(valid_df, geometry=geometry, crs=crs)
            dataset_name = self.derive_dataset_name(source)

            metadata = {
                "sheet_name": selected_sheet,
                "all_sheets": all_sheets,
                "raw_total_rows": len(df),
                "valid_rows": len(valid_df),
                "columns": [str(column) for column in df.columns],
            }

            dataset = SpatialDataset(
                gdf=gdf,
                name=dataset_name,
                lat_col=resolved_lat,
                lon_col=resolved_lon,
                group_col=resolved_group,
                source_path=source_path,
                metadata=metadata,
            )
            return Ok(dataset)
        except Exception as e:
            return Err(
                SpatialError(
                    code=SpatialErrorCode.FileNotFound,
                    message=f"Excel parsing exception: {e}",
                    source_path=str(source),
                    details=str(e),
                )
            )
