"""Pure cartographic design decisions.

This module is the functional core of the static map renderer.  It contains no
network, filesystem, Cartopy, or Matplotlib calls: a map style is resolved into
an immutable layer specification, and data groups are resolved into stable
symbols before the imperative renderer draws anything.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy.spatial.distance import pdist, squareform

from core.domain import MapStyle


class BaseLayer(Enum):
    HYPSOMETRIC = "hypsometric"
    LIGHT_BASEMAP = "light_basemap"


@dataclass(frozen=True)
class MapPalette:
    """All colors needed by a publication rendering contract."""

    terrain_stops: tuple[tuple[float, str], ...]
    categorical: tuple[str, ...]
    water_fill: str
    water_edge: str
    river: str
    river_casing: str
    boundary: str
    text: str
    halo: str


@dataclass(frozen=True)
class HydrographySpec:
    resolution: str
    max_river_rank: int
    max_rivers: int
    river_width: float
    river_casing_width: float
    lake_alpha: float


@dataclass(frozen=True)
class MapRenderSpec:
    """Immutable layer contract consumed by the imperative rendering shell."""

    style: MapStyle
    base_layer: BaseLayer
    basemap_alpha: float
    hillshade_alpha: float
    hydrography: HydrographySpec
    palette: MapPalette


@dataclass(frozen=True)
class GroupSymbol:
    group: object
    marker: str
    color: str


@dataclass(frozen=True)
class GridLabelSpec:
    """Visible coordinate-label sides after reserving an external panel."""

    top: bool = True
    bottom: bool = True
    left: bool = True
    right: bool = True


# High-contrast, color-vision-deficiency friendly colors based on the
# Okabe-Ito family. They are intentionally vivid enough for an illustrative
# map while retaining distinct lightness values in print.
PUBLICATION_CATEGORICAL = (
    "#0067B1",
    "#E64B35",
    "#00A676",
    "#D64D9B",
    "#F4A300",
    "#7656A6",
    "#9A9B00",
    "#53636D",
)

PUBLICATION_MARKERS = (
    "o",
    "s",
    "^",
    "D",
    "v",
    "P",
    "X",
    "*",
    "p",
    "h",
    "<",
    ">",
)

# An illustrative natural-elevation ramp with deliberate hue and lightness
# separation. It is livelier than the reference TIFF without reverting to the
# uniform saturated-green wash produced by Matplotlib's ``terrain``.
PUBLICATION_TERRAIN_STOPS = (
    (0.00, "#176B52"),
    (0.14, "#2F9963"),
    (0.30, "#72BF66"),
    (0.46, "#C8D85C"),
    (0.60, "#EDC957"),
    (0.73, "#D98A4E"),
    (0.84, "#A95F48"),
    (0.93, "#8A665B"),
    (0.98, "#D8D0C1"),
    (1.00, "#FFFDF5"),
)

PUBLICATION_PALETTE = MapPalette(
    terrain_stops=PUBLICATION_TERRAIN_STOPS,
    categorical=PUBLICATION_CATEGORICAL,
    water_fill="#52C1D8",
    water_edge="#006B92",
    river="#008FC4",
    river_casing="#F9F5E8",
    boundary="#28373E",
    text="#172126",
    halo="#FFFFFF",
)


def resolve_map_style(style: MapStyle | str) -> MapStyle:
    """Resolve public and legacy style names without rendering side effects."""

    if isinstance(style, MapStyle):
        return style

    normalized = str(style).strip().lower()
    aliases = {
        "topological": MapStyle.TOPO,
        "topologico": MapStyle.TOPO,
        "topographic": MapStyle.TOPO,
        "topo": MapStyle.TOPO,
        "publicacion": MapStyle.HYBRID_AQUATIC,
        "publication": MapStyle.HYBRID_AQUATIC,
        "hybrid": MapStyle.HYBRID_AQUATIC,
        "hybrid1": MapStyle.HYBRID_AQUATIC,
        "dem_plus_basemap": MapStyle.HYBRID_AQUATIC,
        "clean_png": MapStyle.BASEMAP,
        "clean_basemap": MapStyle.BASEMAP,
    }
    if normalized in aliases:
        return aliases[normalized]
    return MapStyle(normalized)


def build_render_spec(
    style: MapStyle | str,
    *,
    configured_hillshade_alpha: float | None = None,
) -> MapRenderSpec:
    """Build the complete, immutable layer plan for one output style."""

    resolved = resolve_map_style(style)
    configured_alpha = (
        min(0.32, max(0.0, float(configured_hillshade_alpha)))
        if configured_hillshade_alpha is not None
        else None
    )

    if resolved is MapStyle.TOPO:
        return MapRenderSpec(
            style=resolved,
            base_layer=BaseLayer.HYPSOMETRIC,
            basemap_alpha=0.0,
            hillshade_alpha=configured_alpha if configured_alpha is not None else 0.20,
            hydrography=HydrographySpec("10m", 9, 10, 1.05, 2.0, 0.72),
            palette=PUBLICATION_PALETTE,
        )
    if resolved is MapStyle.HYBRID_AQUATIC:
        return MapRenderSpec(
            style=resolved,
            base_layer=BaseLayer.HYPSOMETRIC,
            basemap_alpha=0.85,
            hillshade_alpha=configured_alpha if configured_alpha is not None else 0.22,
            hydrography=HydrographySpec("10m", 9, 12, 1.65, 2.8, 0.82),
            palette=PUBLICATION_PALETTE,
        )
    return MapRenderSpec(
        style=resolved,
        base_layer=BaseLayer.LIGHT_BASEMAP,
        basemap_alpha=1.0,
        hillshade_alpha=0.0,
        hydrography=HydrographySpec("10m", 8, 8, 0.9, 1.7, 0.62),
        palette=PUBLICATION_PALETTE,
    )


def assign_group_symbols(
    groups: Iterable[object],
    *,
    colors: Iterable[str] | None = None,
    markers: Iterable[str] | None = None,
) -> tuple[GroupSymbol, ...]:
    """Assign deterministic marker/color pairs to groups."""

    palette = tuple(colors or PUBLICATION_CATEGORICAL)
    marker_set = tuple(markers or PUBLICATION_MARKERS)
    if not palette or not marker_set:
        raise ValueError("At least one marker and one color are required")

    return tuple(
        GroupSymbol(
            group=group,
            marker=marker_set[index % len(marker_set)],
            color=palette[index % len(palette)],
        )
        for index, group in enumerate(groups)
    )


def build_grid_label_spec(
    side_panel_mode: str = "none",
    *,
    inset_is_outside: bool = False,
) -> GridLabelSpec:
    """Hide side labels only when a lone external side panel would collide."""

    reserved_side = side_panel_mode.strip().lower()
    collision_side = (
        reserved_side
        if reserved_side in {"left", "right"} and not inset_is_outside
        else "none"
    )
    return GridLabelSpec(
        top=True,
        bottom=True,
        left=collision_side != "left",
        right=collision_side != "right",
    )


def spread_overlapping_points(
    coordinates: np.ndarray,
    extent: tuple[float, float, float, float] | list[float],
    *,
    threshold_fraction: float = 0.006,
    radius_fraction: float = 0.0045,
) -> np.ndarray:
    """Return a copy with connected clusters spread around their centroid.

    Fractions are relative to the smaller map span, so collision handling stays
    visually consistent for local and regional datasets.
    """

    coords = np.asarray(coordinates, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError("coordinates must be an (n, 2) array")
    if len(coords) < 2:
        return coords.copy()

    min_lon, max_lon, min_lat, max_lat = (float(v) for v in extent)
    span = min(max_lon - min_lon, max_lat - min_lat)
    if span <= 0:
        return coords.copy()

    threshold = span * threshold_fraction
    radius = span * radius_fraction
    distances = squareform(pdist(coords))
    adjacency = distances <= threshold
    np.fill_diagonal(adjacency, False)
    result = coords.copy()
    visited: set[int] = set()

    for start in range(len(coords)):
        if start in visited:
            continue
        stack = [start]
        component: list[int] = []
        while stack:
            index = stack.pop()
            if index in visited:
                continue
            visited.add(index)
            component.append(index)
            stack.extend(int(i) for i in np.flatnonzero(adjacency[index]))

        if len(component) < 2:
            continue
        center = coords[component].mean(axis=0)
        for offset, point_index in enumerate(sorted(component)):
            angle = 2.0 * np.pi * offset / len(component)
            result[point_index] = center + radius * np.array(
                [np.cos(angle), np.sin(angle)]
            )

    return result
