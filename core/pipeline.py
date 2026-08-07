"""Pure planning functions for the cartographic processing pipeline.

This module is the functional core of the application workflow.  It turns
untrusted CLI values into immutable execution plans, but performs no file,
network, clock, plotting, or console I/O.
"""

from collections.abc import Iterable
from dataclasses import dataclass
import os

from core.domain import ExportFormat, MapStyle


ALL_MAP_STYLES = (
    MapStyle.TOPO,
    MapStyle.HYBRID_AQUATIC,
    MapStyle.BASEMAP,
)

ALL_EXPORT_FORMATS = (
    ExportFormat.PDF,
    ExportFormat.PNG,
    ExportFormat.TIFF,
    ExportFormat.JPEG_XL,
)

_STYLE_ALIASES = {
    "publicacion": MapStyle.HYBRID_AQUATIC,
    "publication": MapStyle.HYBRID_AQUATIC,
    "hybrid": MapStyle.HYBRID_AQUATIC,
    "hybrid_aquatic": MapStyle.HYBRID_AQUATIC,
    "hybrid1": MapStyle.HYBRID_AQUATIC,
    "dem_plus_basemap": MapStyle.HYBRID_AQUATIC,
    "topological": MapStyle.TOPO,
    "topologico": MapStyle.TOPO,
    "topo": MapStyle.TOPO,
    "topographic": MapStyle.TOPO,
    "basemap": MapStyle.BASEMAP,
    "clean_png": MapStyle.BASEMAP,
    "clean_basemap": MapStyle.BASEMAP,
}

_FORMAT_ALIASES = {
    "pdf": ExportFormat.PDF,
    "png": ExportFormat.PNG,
    "tif": ExportFormat.TIFF,
    "tiff": ExportFormat.TIFF,
    "jxl": ExportFormat.JPEG_XL,
    "jpegxl": ExportFormat.JPEG_XL,
}


@dataclass(frozen=True)
class RenderSelection:
    """Closed, immutable plan for the output matrix of one dataset."""

    styles: tuple[MapStyle, ...]
    formats: tuple[ExportFormat, ...]
    include_web_map: bool

    @property
    def expected_artifact_names(self) -> tuple[str, ...]:
        static_names = tuple(
            artifact_filename(style, export_format)
            for style in self.styles
            for export_format in self.formats
        )
        if self.include_web_map:
            return (*static_names, "mapa_interactivo.html")
        return static_names


@dataclass(frozen=True)
class CartographyOverrides:
    """Optional presentation overrides supplied by a driving adapter."""

    with_legend: str | bool | None = None
    show_point_labels: bool | None = None
    show_elevation_colorbar: bool | None = None
    show_inset: bool | None = None
    inset_position: str | tuple[float, ...] | None = None


@dataclass(frozen=True)
class DatasetRunOptions:
    """Technology-neutral values required to process one spatial dataset."""

    render: RenderSelection
    output_dir: str = "output"
    unique_dirs: bool = False
    dpi: int = 500
    padding: float = 0.35
    lat_col: str | None = None
    lon_col: str | None = None
    group_col: str | None = None
    crs: str = "EPSG:4326"
    overrides: CartographyOverrides = CartographyOverrides()


def _normalized(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(value).strip().lower() for value in values)


def resolve_render_selection(
    selected_styles: Iterable[str],
    selected_formats: Iterable[str],
    *,
    include_web_map: bool,
) -> RenderSelection:
    """Resolve aliases and legacy flags into a deterministic render plan."""

    style_tokens = _normalized(selected_styles)
    format_tokens = _normalized(selected_formats)

    styles: list[MapStyle] = list(ALL_MAP_STYLES) if "all" in style_tokens else []
    if "all" not in style_tokens:
        for token in style_tokens:
            # Preserve the historical fallback for unknown style names.
            style = _STYLE_ALIASES.get(token, MapStyle.HYBRID_AQUATIC)
            if style not in styles:
                styles.append(style)

    formats: list[ExportFormat] = []
    if "all" in format_tokens:
        formats.extend(ALL_EXPORT_FORMATS)

    effective_web_map = include_web_map
    for token in format_tokens:
        if export_format := _FORMAT_ALIASES.get(token):
            if export_format not in formats:
                formats.append(export_format)
        elif token in {"web", "web_html", "html"}:
            effective_web_map = True
        elif token == "hybrid1":
            if MapStyle.HYBRID_AQUATIC not in styles:
                styles.append(MapStyle.HYBRID_AQUATIC)
            if ExportFormat.PNG not in formats:
                formats.append(ExportFormat.PNG)
        elif token == "clean_png":
            if MapStyle.BASEMAP not in styles:
                styles.append(MapStyle.BASEMAP)
            if ExportFormat.PNG not in formats:
                formats.append(ExportFormat.PNG)

    return RenderSelection(
        styles=tuple(styles),
        formats=tuple(formats),
        include_web_map=effective_web_map,
    )


def artifact_filename(style: MapStyle, export_format: ExportFormat) -> str:
    """Return the stable public filename for one static map artifact."""

    stem = {
        MapStyle.TOPO: "mapa_topologico",
        MapStyle.HYBRID_AQUATIC: "mapa_publicacion",
        MapStyle.BASEMAP: "mapa_basemap",
    }[style]
    return f"{stem}.{export_format.value}"


def dataset_output_directory(
    base_output_dir: str,
    dataset_name: str,
    *,
    unique_dirs: bool,
    timestamp: str,
) -> str:
    """Purely derive a dataset output path from explicit values."""

    directory_name = f"{dataset_name}_{timestamp}" if unique_dirs else dataset_name
    return os.path.join(base_output_dir, directory_name)
