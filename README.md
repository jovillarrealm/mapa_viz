# 🗺️ GEO MAP GENERATOR (`mapa_viz`)

This is vibe coded. I will give this code some love and poor engineering decisions from my own head eventally, but as it stands, this is more vibe coding, less agentic engineering. 

> **Automated Cartographic Pipeline for Ichthyology & Geographic Information Systems (GIS)**
> Powered by Python 3.14+, `uv`, `Cartopy`, `GeoPandas`, and a **Functional Core, Imperative Shell (FCIS)** architecture with Rust-inspired type safety (`Result[T, E]`).

---

## ✨ Key Features

- 📄 **300 DPI Publication-Grade Cartography**: Renders vector PDFs, high-resolution PNGs, press-ready TIFFs, ultra-compact JPEG XL (`.jxl`), and GPU-accelerated interactive web maps (HTML).
- 🌊 **Zero-Distortion Aquatic Basemap Overlay**: Uses Web Mercator tile-grid bounds stitching to eliminate aspect ratio distortion between elevation topology and aquatic layers.
- 📉 **Journal File Size Limit Optimization (< 10MB)**: Uses Adobe Deflate and LZW compression algorithms for TIFF and PNG formats to guarantee compliance with academic journal upload constraints (< 10 MB per file).
- 🦀 **Rust-Inspired `Result[T, E]` Error Handling**: Eliminates silent exceptions and `NoneType` crashes using explicit `Ok[T]` and `Err[E]` monads with Python 3.14 `match / case` pattern matching.
- 🖥️ **Interactive Terminal CLI**: Built with `rich` panels and `questionary` interactive prompts for easy dataset selection, format toggles, and cartographic customization.
- 🧩 **Data Adapter Architecture**: Decouples input file formats (Excel, CSV, TSV, GeoJSON, GPKG, Shapefile) from cartographic rendering engines.

---

## 🛠️ Python Toolchain & Requirements

This project uses modern Python standards:

- **Python Version**: `Python 3.14+`
- **Package Manager**: `uv` (Fast Python package manager)
- **Linter & Formatter**: `ruff`
- **Static Type Checker**: `ty`
- **Test Runner**: `pytest`

---

## 🚀 Quickstart & Installation

### 1. Clone & Sync Environment

```bash
# Sync environment dependencies and install local package in editable mode
uv sync
```

### 2. Launch Interactive CLI Menu

Run the pipeline interactively to pick datasets, format options, legend toggles, and DPI targets:

```bash
uv run geo-map-generator
# or
uv run main.py
```

---

## 💻 CLI Usage Options & Decoupled Matrix Rendering

Map visual styles (**Axis 1**) and export container formats (**Axis 2**) are completely decoupled:

- **Axis 1: Map Styles (`-s, --styles`)**: `topo`, `hybrid_aquatic`, `basemap`, `all`
- **Axis 2: Export Formats (`-f, --formats`)**: `pdf`, `png`, `tif`, `jxl`, `all`
- **Interactive Web Map**: Handled independently via `--no-web` or interactive prompt.

Static styles share one ordered publication stack:

| Style | Base | Relief | Hydrography |
| :--- | :--- | :--- | :--- |
| `topo` | Vivid illustrative hypsometric DEM | Physically scaled AWS DEM hillshade | High-contrast Natural Earth lakes and selected rivers |
| `hybrid_aquatic` / `publicacion` | Vivid DEM + translucent CartoDB context | Physically scaled AWS DEM hillshade | Saturated-blue basemap water/drainage plus emphasized Natural Earth lakes and rivers |
| `basemap` | CartoDB Light, no labels | None | Minimal Natural Earth hydrography |

AWS Web Mercator tiles are reprojected and cropped to the exact WGS84 map extent before rendering. This is what keeps relief, Natural Earth vectors, rivers, and markers spatially aligned.

### Non-Interactive Command Examples

```bash
# Process all datasets in inputs/ generating all styles in all formats at 300 DPI
uv run main.py -i inputs

# Export Hybrid Aquatic maps in PDF and JXL formats with Legend enabled
uv run main.py -i inputs/coordenadas_mapa_Hypostomus_Liseth.xlsx --styles hybrid_aquatic --formats pdf jxl --show-legend

# Export Topographic & Clean Basemap styles in TIFF (Deflate) format
uv run main.py -i inputs --styles topo basemap --formats tif --dpi 300

# Hide text point labels and elevation colorbar
uv run main.py -i inputs --hide-labels --hide-colorbar
```

### 🎛️ CLI Options Reference

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Input Source** | `-i, --input` | Input file or directory path (omit for Interactive Menu) | `inputs/` |
| **Map Styles** | `-s, --styles` | Space-separated map styles (`topo`, `hybrid_aquatic`, `basemap`, `all`) | `all` |
| **Export Formats** | `-f, --formats` | Space-separated export formats (`pdf`, `png`, `tif`, `jxl`, `all`) | `png pdf jxl` |
| **Disable Web Map**| `--no-web` | Skip GPU interactive HTML web map generation | `false` |
| **Legend Toggle** | `--show-legend` / `--hide-legend` | Explicitly show or hide sampling points legend | `config.yaml` (`false`) |
| **Point Labels** | `--show-labels` / `--hide-labels` | Explicitly show or hide text labels over sampling points | `config.yaml` (`true`) |
| **Colorbar** | `--show-colorbar` / `--hide-colorbar` | Explicitly show or hide elevation colorbar (m.s.n.m.) | `config.yaml` (`false`) |
| **Submap Inset** | `--show-inset` / `--hide-inset` | Explicitly show or hide Colombia submap inset | `config.yaml` (`true`) |
| **DPI Target** | `--dpi` | Target output resolution in DPI (e.g., 300, 600, 1200) | `300` |
| **Output Base** | `-o, --output-dir` | Destination base folder for generated maps | `output/` |
| **Isolated Dirs** | `--unique-dirs` | Append execution timestamp to dataset output directory | `false` |

Without `--unique-dirs`, rerunning a dataset replaces its previous dataset output
directory before rendering. Use `--unique-dirs` when retaining run history is
intentional. The `output/` root contains dataset directories only.

---

## 🏗️ Architecture Overview

```
mapa_viz/
├── core/
│   ├── adapters/            # Data Adapter Architecture (Excel, CSV, Vector, Registry)
│   │   ├── base.py
│   │   ├── csv_adapter.py
│   │   ├── excel_adapter.py
│   │   ├── vector_adapter.py
│   │   └── registry.py
│   ├── result.py            # Result[T, E] Monad (Ok, Err)
│   ├── domain.py            # Immutable Domain Models (BoundingBox, SpatialDataset, ADTs)
│   ├── errors.py            # Explicit Domain Errors (SpatialError)
│   ├── map_design.py        # Pure render specs, palettes, symbols, and collision transforms
│   ├── cartography.py       # Cartographic Rendering Engine (Cartopy, Matplotlib)
│   ├── dem_handler.py       # DEM fetching, WGS84 reprojection/crop, and physical hillshade
│   ├── web_exporter.py      # Interactive Web Map HTML (Folium)
│   ├── cli.py               # Rich Interactive Terminal Menu
│   └── loader.py            # Ingestion helper
├── inputs/                  # Input Excel / CSV / Vector spatial datasets
├── output/                  # Isolated output directories per dataset
├── tests/                   # Pytest test suite
├── adapter_prompt.md        # Prompt specification for AI/Developer custom adapters
├── config.yaml              # System configuration
├── pyproject.toml           # Project metadata & dependencies
└── README.md                # Project documentation
```

The FCIS boundary is explicit: `map_design.py` is the functional core that resolves immutable layer contracts and symbol assignments; `main.py`, `dem_handler.py`, and `cartography.py` form the imperative shell that performs I/O, raster reprojection, drawing, and export.

### 🧩 Adding Custom Data Adapters

New input sources (e.g. PostGIS, KML, JSON APIs) can be added by implementing a subclass of `BaseDataAdapter` in `core/adapters/`. See [`adapter_prompt.md`](adapter_prompt.md) for the exact specification and prompt template.

---

## 🧪 Testing & Quality Assurance

Run the test suite and quality checks:

```bash
# Run Pytest unit & integration tests
uv run pytest

# Run Static Type Checker
uv run ty check core/ main.py tests/

# Run Linter & Formatter
uv run ruff check core/ main.py tests/
uv run ruff format core/ main.py tests/
```

---

## 📄 License

Developed for scientific publication cartography in Ichthyology & Spatial Data Science.
