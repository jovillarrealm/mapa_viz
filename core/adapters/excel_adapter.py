import os
from typing import cast

import geopandas as gpd
import pandas as pd

from core.adapters.base import BaseDataAdapter
from core.coordinates import prepare_spatial_dataframe
from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result
from core.tabular_schema import (
    coordinate_column_score,
    detect_lat_lon_columns,
    ensure_group_column,
)


class ExcelDataAdapter(BaseDataAdapter):
    """
    Adapter for Microsoft Excel files (.xlsx, .xls).
    Inspects sheets, auto-detects latitude/longitude columns, validates coordinates,
    maps grouping categories, and builds SpatialDataset wrapped in Result[SpatialDataset, SpatialError].
    """

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
            score = coordinate_column_score(df_parsed.columns)
            if score > max_coord_score:
                max_coord_score = score
                best_sheet = sheet

        return best_sheet

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

            detected_cols = detect_lat_lon_columns(df, lat_col, lon_col)
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
            df, resolved_group = ensure_group_column(df, group_col)

            prep_result = prepare_spatial_dataframe(
                df, lat_col=resolved_lat, lon_col=resolved_lon, source_crs=crs
            )
            if isinstance(prep_result, Err):
                error = cast(SpatialError, prep_result.error)
                return Err(
                    SpatialError(
                        code=error.code,
                        message=error.message,
                        source_path=source_path,
                        details=error.details,
                    )
                )
            gdf, effective_crs = prep_result.unwrap()

            dataset_name = self.derive_dataset_name(source)

            metadata = {
                "sheet_name": selected_sheet,
                "all_sheets": all_sheets,
                "raw_total_rows": len(df),
                "valid_rows": len(gdf),
                "columns": [str(column) for column in df.columns],
                "crs": effective_crs,
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
