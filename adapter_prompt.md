# PROMPT SPECIFICATION: GENERATING CUSTOM DATA ADAPTERS FOR MAP_VIZ

This document defines the prompt specification and instructions for an AI Agent or Developer to build custom **Data Adapters** for any input format (Excel, CSV, GeoJSON, KML, XML, JSON APIs, PostGIS, etc.) in the `geo_map_generator` system.

---

## 🎯 Objective & Architectural Pattern

The `geo_map_generator` system uses the **Adapter Design Pattern** to decouple raw heterogenous input sources from cartographic rendering engines (Matplotlib, Cartopy, Deck.gl).

All data adapters convert external input files or data streams into a standardized internal representation object: **`SpatialDatasetRepresentation`**.

```text
[ Raw Input Source ] ──► [ Custom Adapter (inherits BaseDataAdapter) ] ──► [ SpatialDatasetRepresentation ] ──► [ Cartography Engine ]
```

---

## 📐 Internal Data Contract: `SpatialDatasetRepresentation`

Every adapter MUST return an instance of `SpatialDatasetRepresentation` (defined in `core/adapters/base.py`) with the following fields:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `gdf` | `geopandas.GeoDataFrame` | GeoDataFrame containing point geometries in WGS84 (`EPSG:4326`). |
| `dataset_name` | `str` | Clean, filesystem-safe identifier derived from the source file (e.g. `Cordylancistrus`). |
| `lat_col` | `str` | Name of the column containing Latitude values. |
| `lon_col` | `str` | Name of the column containing Longitude values. |
| `group_col` | `str` | Column name used for grouping markers and legend (e.g., `Sector`, `Species`, `Drainage`). |
| `source_path` | `str` | Path or identifier of the raw source input. |
| `metadata` | `dict` | Dictionary containing sheet names, total rows, CRS info, or custom attributes. |

---

## 🛠️ Step-by-Step Prompt to Generate a Custom Adapter

When asking an AI model or developer to create a new adapter, provide this prompt:

```text
You are an expert Python Geospatial Software Engineer.
Your task is to implement a custom Data Adapter for `geo_map_generator` that handles the input format: `<FORMAT_OR_FILE_STRUCTURE>`.

Requirements:
1. Create a class `<CustomFormat>Adapter` that inherits from `BaseDataAdapter` (`core.adapters.base.BaseDataAdapter`).
2. Implement `can_handle(self, source: DataSource) -> bool`:
   - Returns True if `source` matches the target file extension or data type.
3. Implement the fully typed `adapt(self, source: DataSource, lat_col: str | None = None, lon_col: str | None = None, group_col: str | None = None, sheet_name: str | None = None, crs: str = "EPSG:4326", sep: str | None = None) -> Result[SpatialDataset, SpatialError]` contract:
   - Parse raw coordinates and handle missing/invalid values cleanly.
   - Detect or accept latitude/longitude columns (handling coordinate variations like `decimalLatitud`, `Latitud decimal`, `X`, `Y`, GMS degrees, etc.).
   - Handle swapping if X is Latitude and Y is Longitude or vice-versa.
   - Standardize point geometries in WGS84 (`EPSG:4326`).
   - Identify or assign a valid grouping column (`group_col`).
   - Construct and return `SpatialDatasetRepresentation`.
4. Register the adapter in `DataAdapterRegistry` (`core.adapters.registry.registry.register(<CustomFormat>Adapter())`).
```

---

## 💡 Example: Writing a KML / XML Data Adapter

Below is an example of an adapter built using this architecture:

```python
import os
import geopandas as gpd
import fiona

from core.adapters.base import BaseDataAdapter, SpatialDatasetRepresentation
from core.domain import DataSource
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result

class KMLDataAdapter(BaseDataAdapter):
    """Custom Data Adapter for Keyhole Markup Language (.kml) files."""
    
    def can_handle(self, source: DataSource) -> bool:
        return not isinstance(source, gpd.GeoDataFrame) and os.fspath(source).lower().endswith(".kml")

    def adapt(
        self,
        source: DataSource,
        lat_col: str | None = None,
        lon_col: str | None = None,
        group_col: str | None = None,
        sheet_name: str | None = None,
        crs: str = "EPSG:4326",
        sep: str | None = None,
    ) -> Result[SpatialDatasetRepresentation, SpatialError]:
        if isinstance(source, gpd.GeoDataFrame) or not self.can_handle(source):
            return Err(SpatialError(
                code=SpatialErrorCode.UnsupportedFormat,
                message=f"Cannot process KML source '{source}'",
            ))
        source_path = os.fspath(source)
        fiona.drvsupport.supported_drivers['KML'] = 'rw'
        gdf = gpd.read_file(source_path, driver='KML')
        
        if gdf.crs is None:
            gdf.set_crs(crs, inplace=True)
        else:
            gdf = gdf.to_crs(crs)
            
        gdf['latitude'] = gdf.geometry.y
        gdf['longitude'] = gdf.geometry.x
        
        if "Name" in gdf.columns:
            gdf["Group"] = gdf["Name"]
            resolved_group = "Group"
        else:
            gdf["Group"] = "KML_Points"
            resolved_group = "Group"
            
        dataset_name = self.derive_dataset_name(source)
        
        return Ok(SpatialDatasetRepresentation(
            gdf=gdf,
            name=dataset_name,
            lat_col="latitude",
            lon_col="longitude",
            group_col=resolved_group,
            source_path=source_path,
            metadata={"driver": "KML", "total_features": len(gdf)}
        ))
```

---

## 🔄 Automatic Adapter Discovery & Registration

Every newly created adapter can be registered dynamically at runtime without modifying core code:

```python
from core.adapters import registry
from my_custom_adapters import KMLDataAdapter

# Register custom adapter
registry.register(KMLDataAdapter())

# Automatically ingests .kml file via newly registered adapter!
representation = registry.load("inputs/field_survey.kml")
```
