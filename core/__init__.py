"""
Core package for geo_map_generator.
Includes data ingestion, DEM elevation & hillshade processing, cartographic layout building, and web exporting.
"""

from .cartography import create_publication_map
from .dem_handler import get_dem_and_hillshade
from .loader import load_spatial_data
from .web_exporter import export_web_map

__all__ = [
    "create_publication_map",
    "export_web_map",
    "get_dem_and_hillshade",
    "load_spatial_data",
]
