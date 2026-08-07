import geopandas as gpd
import pandas as pd

from core.adapters.registry import load_dataset
from core.result import Err
from core.tabular_schema import detect_lat_lon_columns as infer_lat_lon_columns


def detect_lat_lon_columns(
    df: pd.DataFrame,
    lat_col: str | None = None,
    lon_col: str | None = None,
) -> tuple[str, str]:
    """Backwards compatibility wrapper for shared schema inference."""
    cols = infer_lat_lon_columns(df, lat_col, lon_col)
    if cols is None:
        raise ValueError(
            f"Failed to detect Latitude and Longitude columns. Columns: {list(df.columns)}"
        )
    return cols


def load_spatial_data(
    input_source: str | pd.DataFrame | gpd.GeoDataFrame,
    lat_col: str | None = None,
    lon_col: str | None = None,
    group_col: str = "Sector",
    crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    """
    Ingests tabular or vector data using the Data Adapter Architecture.
    Unwraps Result[SpatialDataset, SpatialError] or raises ValueError on error.
    """
    result = load_dataset(
        input_source,
        lat_col=lat_col,
        lon_col=lon_col,
        group_col=group_col,
        crs=crs,
    )
    if isinstance(result, Err):
        raise ValueError(str(result.error))

    dataset = result.unwrap()
    print(
        f"[Loader] Ingested dataset '{dataset.name}' ({dataset.num_points} points). "
        f"Mapped Lat -> '{dataset.lat_col}', Lon -> '{dataset.lon_col}', Group -> '{dataset.group_col}'"
    )
    return dataset.gdf
