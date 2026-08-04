from dataclasses import dataclass, field
from enum import Enum
from os import PathLike
from collections.abc import Mapping
from typing import NotRequired, TypedDict

import geopandas as gpd
import pandas as pd


type DataSource = str | PathLike[str] | pd.DataFrame
type MetadataValue = str | int | float | bool | None | list[str]


class ProcessingSummary(TypedDict):
    dataset_name: str
    num_points: int
    output_dir: str
    num_files: int
    rendered_files: NotRequired[list[str]]
    error: NotRequired[str]


class MapStyle(Enum):
    """Orthogonal Axis 1: Cartographic Visual Style & Layer Composition."""

    TOPO = "topo"
    HYBRID_AQUATIC = "hybrid_aquatic"
    HYBRID_RELIEF = "hybrid_relief"
    BASEMAP = "basemap"


class ExportFormat(Enum):
    """Orthogonal Axis 2: Export File Container & Compression Format."""

    PDF = "pdf"
    PNG = "png"
    TIFF = "tif"
    JPEG_XL = "jxl"


# Alias for backwards compatibility
MapFormat = ExportFormat


class DpiTarget(Enum):
    Journal300 = 300
    HighRes600 = 600
    UltraRes1200 = 1200


@dataclass(frozen=True)
class BoundingBox:
    """Immutable Geographic Bounding Box [min_lon, min_lat, max_lon, max_lat]."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def with_padding(self, padding_deg: float = 0.35) -> BoundingBox:
        """Pure method returning a new BoundingBox with padding applied."""
        return BoundingBox(
            min_lon=self.min_lon - padding_deg,
            min_lat=self.min_lat - padding_deg,
            max_lon=self.max_lon + padding_deg,
            max_lat=self.max_lat + padding_deg,
        )

    def to_extent_tuple(self) -> tuple[float, float, float, float]:
        """Returns Cartopy/Matplotlib extent tuple (min_lon, max_lon, min_lat, max_lat)."""
        return (self.min_lon, self.max_lon, self.min_lat, self.max_lat)

    @classmethod
    def from_gdf(cls, gdf: gpd.GeoDataFrame) -> BoundingBox:
        bounds = gdf.total_bounds
        return cls(
            min_lon=float(bounds[0]),
            min_lat=float(bounds[1]),
            max_lon=float(bounds[2]),
            max_lat=float(bounds[3]),
        )


@dataclass(frozen=True)
class SpatialDataset:
    """
    Immutable Standard Internal Representation for Spatial Tabular/Vector Datasets.
    """

    gdf: gpd.GeoDataFrame
    name: str
    lat_col: str
    lon_col: str
    group_col: str
    source_path: str
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    @property
    def num_points(self) -> int:
        return len(self.gdf)

    @property
    def bbox(self) -> BoundingBox:
        return BoundingBox.from_gdf(self.gdf)
