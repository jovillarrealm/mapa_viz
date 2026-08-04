import os

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from core.adapters.base import BaseDataAdapter
from core.adapters.excel_adapter import ExcelDataAdapter
from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result


class CSVDataAdapter(BaseDataAdapter):
    """
    Adapter for CSV, TSV, and TXT delimited files.
    Auto-detects delimiters, latitude/longitude columns, and grouping attributes.
    Returns Result[SpatialDataset, SpatialError].
    """

    def can_handle(self, source: DataSource) -> bool:
        if isinstance(source, pd.DataFrame):
            return False
        ext = os.path.splitext(os.fspath(source))[1].lower()
        return ext in [".csv", ".tsv", ".txt"]

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
        if isinstance(source, pd.DataFrame) or not self.can_handle(source):
            return Err(
                SpatialError(
                    code=SpatialErrorCode.UnsupportedFormat,
                    message=f"Cannot process CSV source '{source}'",
                    source_path=str(source),
                )
            )

        source_path = os.fspath(source)
        if sep is None:
            ext = os.path.splitext(source_path)[1].lower()
            sep = "\t" if ext == ".tsv" else ","

        try:
            try:
                df = pd.read_csv(source_path, sep=sep)
            except Exception:
                df = pd.read_csv(source_path, sep=None, engine="python")

            excel_helper = ExcelDataAdapter()
            detected_cols = excel_helper._detect_lat_lon_columns(df, lat_col, lon_col)
            if detected_cols is None:
                return Err(
                    SpatialError(
                        code=SpatialErrorCode.MissingCoordinates,
                        message=f"Failed to detect Latitude and Longitude columns in CSV file '{source}'",
                        source_path=str(source),
                        details=f"Available columns: {list(df.columns)}",
                    )
                )

            resolved_lat, resolved_lon = detected_cols
            resolved_group = excel_helper._detect_group_column(df, group_col)

            df[resolved_lat] = pd.to_numeric(df[resolved_lat], errors="coerce")
            df[resolved_lon] = pd.to_numeric(df[resolved_lon], errors="coerce")
            valid_df = df.dropna(subset=[resolved_lat, resolved_lon]).copy()

            if len(valid_df) == 0:
                return Err(
                    SpatialError(
                        code=SpatialErrorCode.EmptyDataset,
                        message="No valid coordinate rows remaining after parsing CSV",
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
                "delimiter": sep,
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
                    message=f"CSV reading exception: {e}",
                    source_path=str(source),
                    details=str(e),
                )
            )
