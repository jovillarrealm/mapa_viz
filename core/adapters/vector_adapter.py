import os

import geopandas as gpd
import pandas as pd

from core.adapters.base import BaseDataAdapter
from core.adapters.excel_adapter import ExcelDataAdapter
from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result


class VectorDataAdapter(BaseDataAdapter):
    """
    Adapter for GIS spatial vector formats (GeoJSON, GPKG, Shapefile, Parquet, GeoDataFrame).
    Returns Result[SpatialDataset, SpatialError].
    """

    def can_handle(self, source: DataSource) -> bool:
        if isinstance(source, gpd.GeoDataFrame):
            return True
        if isinstance(source, pd.DataFrame):
            return False
        ext = os.path.splitext(os.fspath(source))[1].lower()
        return ext in [".geojson", ".gpkg", ".shp", ".parquet", ".json"]

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
        if not self.can_handle(source):
            return Err(
                SpatialError(
                    code=SpatialErrorCode.UnsupportedFormat,
                    message=f"Cannot process vector source '{source}'",
                    source_path=str(source),
                )
            )

        try:
            if isinstance(source, gpd.GeoDataFrame):
                gdf = source.copy()
                source_path = "GeoDataFrame"
                dataset_name = "InMemoryDataset"
            elif not isinstance(source, pd.DataFrame):
                source_path = os.fspath(source)
                gdf = gpd.read_file(source_path)
                dataset_name = self.derive_dataset_name(source)
            else:
                return Err(
                    SpatialError(
                        code=SpatialErrorCode.UnsupportedFormat,
                        message="A plain DataFrame is not a vector source",
                    )
                )

            if gdf.crs is None:
                gdf.set_crs(crs, inplace=True)
            else:
                gdf = gdf.to_crs(crs)

            excel_helper = ExcelDataAdapter()
            resolved_group = excel_helper._detect_group_column(gdf, group_col)

            lat_name = lat_col or "latitude"
            lon_name = lon_col or "longitude"

            if lat_name not in gdf.columns:
                gdf[lat_name] = gdf.geometry.y
            if lon_name not in gdf.columns:
                gdf[lon_name] = gdf.geometry.x

            metadata = {
                "driver": "Vector",
                "crs": str(gdf.crs),
                "raw_total_rows": len(gdf),
                "valid_rows": len(gdf),
                "columns": [str(column) for column in gdf.columns],
            }

            dataset = SpatialDataset(
                gdf=gdf,
                name=dataset_name,
                lat_col=lat_name,
                lon_col=lon_name,
                group_col=resolved_group,
                source_path=source_path,
                metadata=metadata,
            )
            return Ok(dataset)
        except Exception as e:
            return Err(
                SpatialError(
                    code=SpatialErrorCode.FileNotFound,
                    message=f"Vector reading exception: {e}",
                    source_path=str(source),
                    details=str(e),
                )
            )
