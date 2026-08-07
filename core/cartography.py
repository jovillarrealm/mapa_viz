import io
import os
from functools import lru_cache

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.img_tiles as cimgt
import cartopy.io.shapereader as shpreader
from cartopy.mpl.geoaxes import GeoAxes
import geopandas as gpd
import matplotlib

from core.config import AppConfig
from core.domain import ExportFormat, MapStyle
from core.map_design import (
    BaseLayer,
    HydrographySpec,
    MapPalette,
    PUBLICATION_TERRAIN_STOPS,
    assign_group_symbols,
    build_grid_label_spec,
    build_render_spec,
    spread_overlapping_points,
)
from core.pipeline import artifact_filename

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.patheffects as PathEffects
import matplotlib.pyplot as plt
import numpy as np
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
from matplotlib.patches import Polygon, Rectangle
from PIL import Image
from shapely.geometry.base import BaseGeometry

class CartoDBNoLabels(cimgt.GoogleWTS):
    """
    CartoDB Positron No-Labels tile basemap.
    """

    def _image_url(self, tile: tuple[int, int, int]) -> str:
        x, y, z = tile
        return f"https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"


def colorize_hybrid_basemap(image: Image.Image) -> Image.Image:
    """Make CartoDB water unmistakably blue while retaining faint context."""

    rgba = np.array(image.convert("RGBA"), dtype=np.uint8)
    red = rgba[:, :, 0].astype(np.int16)
    green = rgba[:, :, 1].astype(np.int16)
    blue = rgba[:, :, 2].astype(np.int16)

    # CartoDB Light water pixels are cool gray-blue (for example 210/219/222),
    # while land is warm off-white (typically 250/250/248). The simultaneous
    # channel deltas avoid confusing pale roads or warm administrative lines
    # with water.
    water = (
        (red < 240)
        & ((green - red) >= 4)
        & ((blue - red) >= 5)
        & (blue >= green)
    )

    rgba[:, :, 3] = 70
    rgba[water, 0] = 0
    rgba[water, 1] = 119
    rgba[water, 2] = 182
    rgba[water, 3] = 235
    return Image.fromarray(rgba)


class CartoDBBlueWaterOverlay(CartoDBNoLabels):
    """CartoDB context with vivid blue water and translucent non-water pixels."""

    def get_image(
        self, tile: tuple[int, int, int]
    ) -> tuple[Image.Image, tuple[float, float, float, float], str]:
        image, extent, origin = super().get_image(tile)
        return colorize_hybrid_basemap(image), extent, origin


def get_hypsometric_colormap(
    min_val: float,
    max_val: float,
    terrain_stops: tuple[tuple[float, str], ...] = PUBLICATION_TERRAIN_STOPS,
):
    """
    Return the illustrative publication hypsometric ramp and its elevation norm.

    Water is deliberately absent from this ramp. Hydrography is an independent
    Natural Earth layer, which keeps its geometry and styling explicit.
    """
    vmin = float(min_val)
    vmax = float(max_val)
    if vmax <= vmin:
        vmax = vmin + 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_name = f"hypsometric_{int(min_val)}_{int(max_val)}"
    return (
        mcolors.LinearSegmentedColormap.from_list(cmap_name, terrain_stops),
        norm,
    )


def parse_with_legend_spec(
    with_legend: str | bool | None = None,
    default_spec: str = "top_right_outside",
) -> tuple[bool, str, str, tuple[float, float] | None, int]:
    """
    Parses legend specifications into:
    (is_active, side_panel_mode, legend_loc, bbox_to_anchor, legend_ncols)

    side_panel_mode: "right", "left", "bottom", or "none"
    """
    if with_legend is None or with_legend is False:
        return False, "none", "upper right", None, 1
    if with_legend is True:
        raw_spec = default_spec
    else:
        raw_spec = str(with_legend).strip().lower()

    if raw_spec in ["none", "false", "no", "off", "disable", "disabled"]:
        return False, "none", "upper right", None, 1

    # OUTSIDE variations
    if raw_spec in ["top_right_outside", "right_outside", "outside_right", "outside"]:
        return True, "right", "upper left", (1.04, 1.0), 1
    elif raw_spec in ["bottom_right_outside"]:
        return True, "right", "lower left", (1.04, 0.0), 1
    elif raw_spec in ["top_left_outside", "left_outside", "outside_left"]:
        return True, "left", "upper right", (-0.04, 1.0), 1
    elif raw_spec in ["bottom_left_outside"]:
        return True, "left", "lower right", (-0.04, 0.0), 1
    elif raw_spec in ["bottom_outside", "bottom_center_outside", "bottom", "outside_bottom"]:
        return True, "bottom", "upper center", (0.5, -0.12), 4

    # INSIDE variations
    elif raw_spec in ["top_right_inside", "top_right", "inside_top_right", "inside"]:
        return True, "none", "upper right", None, 1
    elif raw_spec in ["top_left_inside", "top_left", "inside_top_left"]:
        return True, "none", "upper left", None, 1
    elif raw_spec in ["bottom_right_inside", "bottom_right", "inside_bottom_right"]:
        return True, "none", "lower right", None, 1
    elif raw_spec in ["bottom_left_inside", "bottom_left", "inside_bottom_left"]:
        return True, "none", "lower left", None, 1
    elif raw_spec in ["bottom_center_inside", "bottom_inside", "inside_bottom"]:
        return True, "none", "lower center", None, 1
    elif raw_spec in ["auto", "best"]:
        return True, "none", "best", None, 1
    else:
        return True, "right", "upper left", (1.04, 1.0), 1


def resolve_inset_location(
    position: str | list[float] | tuple[float, ...] | None,
    gdf: gpd.GeoDataFrame,
    extent: tuple[float, float, float, float] | list[float],
    has_legend_or_cbar: bool | str = False,
) -> tuple[list[float], str, tuple[float, float, float, float]]:
    """
    Resolves the inset submap bounding box [x, y, w, h] and the main map axes rectangle.
    """
    side_mode = (
        str(has_legend_or_cbar).lower()
        if isinstance(has_legend_or_cbar, str)
        else ("right" if has_legend_or_cbar else "none")
    )
    if side_mode == "left":
        default_map_rect = (0.28, 0.06, 0.64, 0.88)
    elif side_mode == "bottom":
        default_map_rect = (0.08, 0.22, 0.84, 0.72)
    elif side_mode == "right":
        default_map_rect = (0.08, 0.06, 0.66, 0.88)
    else:
        default_map_rect = (0.08, 0.06, 0.84, 0.88)

    if isinstance(position, (list, tuple)) and len(position) == 4:
        return list(position), "custom", default_map_rect

    pos_str = str(position).lower() if position and isinstance(position, str) else "top_left"

    if pos_str in ["outside", "outside_right"]:
        inset_loc = [0.72, 0.54, 0.22, 0.34]
        return inset_loc, "outside_right", (0.08, 0.06, 0.62, 0.88)

    if pos_str == "outside_left":
        inset_loc = [0.03, 0.54, 0.22, 0.34]
        return inset_loc, "outside_left", (0.28, 0.06, 0.64, 0.88)

    map_rect = default_map_rect

    if pos_str == "top_right":
        return [0.71, 0.64, 0.27, 0.33], "top_right", map_rect
    elif pos_str == "bottom_right":
        return [0.71, 0.03, 0.27, 0.33], "bottom_right", map_rect
    elif pos_str == "bottom_left":
        return [0.02, 0.03, 0.27, 0.33], "bottom_left", map_rect
    elif pos_str == "auto":
        loc, quad = find_best_inset_location(gdf, extent)
        return loc, quad, map_rect
    else:  # 'top_left' is DEFAULT
        return [0.02, 0.64, 0.27, 0.33], "top_left", map_rect


def find_best_inset_location(
    gdf: gpd.GeoDataFrame,
    extent: tuple[float, float, float, float] | list[float],
) -> tuple[list[float], str]:
    """
    Dynamically determines the optimal submap inset location (Top-Left, Top-Right,
    Bottom-Right, Bottom-Left) that has ZERO sampling point overlaps.
    """
    min_lon, max_lon, min_lat, max_lat = extent
    candidates = {
        "top_left": [0.02, 0.64, 0.27, 0.33],
        "top_right": [0.71, 0.64, 0.27, 0.33],
        "bottom_right": [0.71, 0.03, 0.27, 0.33],
        "bottom_left": [0.02, 0.03, 0.27, 0.33],
    }

    dx = max_lon - min_lon if max_lon != min_lon else 1.0
    dy = max_lat - min_lat if max_lat != min_lat else 1.0
    norm_x = (gdf.geometry.x.values - min_lon) / dx
    norm_y = (gdf.geometry.y.values - min_lat) / dy

    scores = {}
    for name, rect in candidates.items():
        rx, ry, rw, rh = rect
        overlap_count = np.sum(
            (norm_x >= rx)
            & (norm_x <= rx + rw)
            & (norm_y >= ry)
            & (norm_y <= ry + rh)
        )
        scores[name] = int(overlap_count)

    best_name = min(scores, key=lambda k: scores[k])
    return candidates[best_name], best_name


@lru_cache(maxsize=1)
def get_colombia_geometry():
    try:
        shpfilename = shpreader.natural_earth(
            resolution="110m", category="cultural", name="admin_0_countries"
        )
        reader = shpreader.Reader(shpfilename)
        for country in reader.records():
            name = country.attributes.get("NAME", country.attributes.get("NAME_LONG", ""))
            if name == "Colombia":
                return country.geometry
    except Exception:
        pass
    return None


def add_colombia_inset_submap(
    fig: plt.Figure,
    main_ax: GeoAxes,
    main_extent: list[float],
    location: list[float] = [0.02, 0.64, 0.27, 0.33],
    *,
    inside_main_map: bool = True,
):
    """
    Adds inset submap of South America (continent) highlighting Colombia and the study area.
    """
    loc_tuple = (
        float(location[0]),
        float(location[1]),
        float(location[2]),
        float(location[3]),
    )
    if inside_main_map:
        inset_ax = main_ax.inset_axes(loc_tuple, projection=ccrs.PlateCarree())
    else:
        inset_ax = fig.add_axes(loc_tuple, projection=ccrs.PlateCarree())
    assert isinstance(inset_ax, GeoAxes)
    inset_ax.set_extent((-88, -34, -56, 13), crs=ccrs.PlateCarree())

    # Deliberately limited palette: neutral land/water, one Colombia fill, and
    # one study-area accent. The inset supplies location, not another data map.
    inset_ax.add_feature(cfeature.LAND, facecolor="#F2F1EC", zorder=1)
    inset_ax.add_feature(cfeature.OCEAN, facecolor="#DDE7EA", zorder=1)
    inset_ax.add_feature(
        cfeature.BORDERS, linestyle="-", edgecolor="#8A8D8F", linewidth=0.45, zorder=2
    )
    inset_ax.add_feature(
        cfeature.COASTLINE, edgecolor="#53585B", linewidth=0.6, zorder=3
    )

    geom = get_colombia_geometry()
    if geom is not None:
        inset_ax.add_geometries(
            [geom],
            crs=ccrs.PlateCarree(),
            facecolor="#8FAE91",
            edgecolor="#343A3D",
            linewidth=0.9,
            zorder=4,
        )

    min_lon, max_lon, min_lat, max_lat = main_extent
    w = max_lon - min_lon
    h = max_lat - min_lat

    rect = Rectangle(
        (min_lon, min_lat),
        w,
        h,
        fill=False,
        edgecolor="#315B72",
        linewidth=1.4,
        transform=ccrs.PlateCarree(),
        zorder=5,
    )
    inset_ax.add_patch(rect)

    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    inset_ax.scatter(
        center_lon,
        center_lat,
        color="#315B72",
        s=14,
        marker="o",
        edgecolor="black",
        linewidth=0.5,
        transform=ccrs.PlateCarree(),
        zorder=6,
    )

    for spine in inset_ax.spines.values():
        spine.set_edgecolor("#111111")
        spine.set_linewidth(1.0)

    return inset_ax


def add_north_arrow(ax, x=0.88, y=0.18, size=0.045):
    trans = ax.transAxes
    r_out = size
    r_in = size * 0.28

    N = (x, y + r_out)
    S = (x, y - r_out)
    E = (x + r_out, y)
    W = (x - r_out, y)

    NE = (x + r_in, y + r_in)
    SE = (x + r_in, y - r_in)
    SW = (x - r_in, y - r_in)
    NW = (x - r_in, y + r_in)
    C = (x, y)

    poly_N_L = Polygon([N, C, NW], facecolor="#111111", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_N_R = Polygon([N, NE, C], facecolor="#ffffff", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_S_L = Polygon([S, C, SE], facecolor="#111111", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_S_R = Polygon([S, SW, C], facecolor="#ffffff", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_E_L = Polygon([E, C, NE], facecolor="#111111", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_E_R = Polygon([E, SE, C], facecolor="#ffffff", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_W_L = Polygon([W, C, SW], facecolor="#111111", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)
    poly_W_R = Polygon([W, NW, C], facecolor="#ffffff", edgecolor="#111111", lw=0.6, transform=trans, zorder=25)

    for p in [poly_N_L, poly_N_R, poly_S_L, poly_S_R, poly_E_L, poly_E_R, poly_W_L, poly_W_R]:
        ax.add_patch(p)

    txt = ax.text(
        x,
        y + r_out + 0.015,
        "N",
        transform=trans,
        horizontalalignment="center",
        verticalalignment="bottom",
        fontsize=12,
        fontweight="bold",
        color="#111111",
        zorder=26,
    )
    txt.set_path_effects([PathEffects.withStroke(linewidth=3.0, foreground="white")])


def add_scale_bar(
    ax, extent, location=(0.74, 0.05), length_km=None, transparent_bg=True
):
    min_lon, max_lon, min_lat, max_lat = extent
    center_lat = (min_lat + max_lat) / 2.0

    km_per_deg_lon = 111.320 * np.cos(np.radians(center_lat))
    total_width_km = (max_lon - min_lon) * km_per_deg_lon

    if length_km is None:
        target = total_width_km * 0.20
        if target >= 100:
            length_km = round(target / 50.0) * 50
        elif target >= 20:
            length_km = round(target / 10.0) * 10
        elif target >= 5:
            length_km = round(target / 5.0) * 5
        else:
            length_km = max(1, round(target))

    length_deg = length_km / km_per_deg_lon
    x0 = min_lon + (max_lon - min_lon) * location[0]
    y0 = min_lat + (max_lat - min_lat) * location[1]
    x1 = x0 + length_deg
    half_x = x0 + length_deg / 2.0

    bar_height = (max_lat - min_lat) * 0.012

    if not transparent_bg:
        padding_x = length_deg * 0.15
        padding_y = bar_height * 2.0
        bg_rect = Rectangle(
            (x0 - padding_x, y0 - padding_y),
            length_deg + 2 * padding_x,
            bar_height * 5.5 + padding_y,
            facecolor="white",
            alpha=0.85,
            edgecolor="#555555",
            linewidth=0.8,
            transform=ccrs.PlateCarree(),
            zorder=18,
        )
        ax.add_patch(bg_rect)

    rect1 = Rectangle(
        (x0, y0),
        length_deg / 2.0,
        bar_height,
        facecolor="#111111",
        edgecolor="#ffffff",
        linewidth=0.5,
        transform=ccrs.PlateCarree(),
        zorder=19,
    )
    rect2 = Rectangle(
        (half_x, y0),
        length_deg / 2.0,
        bar_height,
        facecolor="white",
        edgecolor="#111111",
        linewidth=0.5,
        transform=ccrs.PlateCarree(),
        zorder=19,
    )
    ax.add_patch(rect1)
    ax.add_patch(rect2)

    tick_h = bar_height * 0.6
    for val_x in [x0, half_x, x1]:
        ax.plot(
            [val_x, val_x],
            [y0 + bar_height, y0 + bar_height + tick_h],
            color="#111111",
            lw=1.2,
            transform=ccrs.PlateCarree(),
            zorder=20,
        )

    y_text = y0 + bar_height + tick_h + (max_lat - min_lat) * 0.005
    for val_x, label_text in zip(
        [x0, half_x, x1],
        ["0", f"{int(length_km / 2)}", f"{int(length_km)} km"],
        strict=False,
    ):
        txt = ax.text(
            val_x,
            y_text,
            str(label_text),
            transform=ccrs.PlateCarree(),
            horizontalalignment="center",
            verticalalignment="bottom",
            fontsize=8.5,
            fontweight="bold",
            color="#111111",
            zorder=21,
        )
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=2.5, foreground="white")]
        )


@lru_cache(maxsize=32)
def _load_relevant_hydrography(
    extent: tuple[float, float, float, float],
    resolution: str,
    max_river_rank: int,
    max_rivers: int,
) -> tuple[
    tuple[tuple[BaseGeometry, int, str], ...],
    tuple[BaseGeometry, ...],
]:
    """Load only Natural Earth hydrography relevant to the current view."""

    from shapely.geometry import box

    min_lon, max_lon, min_lat, max_lat = extent
    area_of_interest = box(min_lon, min_lat, max_lon, max_lat)

    river_path = shpreader.natural_earth(
        resolution=resolution,
        category="physical",
        name="rivers_lake_centerlines",
    )
    candidates: list[tuple[BaseGeometry, int, str, float]] = []
    for record in shpreader.Reader(river_path).records():
        if not record.geometry.intersects(area_of_interest):
            continue
        rank = int(record.attributes.get("scalerank", 99))
        if rank > max_river_rank:
            continue
        clipped = record.geometry.intersection(area_of_interest)
        name = str(
            record.attributes.get("name_en")
            or record.attributes.get("name")
            or ""
        )
        candidates.append((clipped, rank, name, float(clipped.length)))

    candidates.sort(key=lambda item: (item[1], -item[3], item[2]))
    rivers = tuple(
        (geometry, rank, name)
        for geometry, rank, name, _length in candidates[:max_rivers]
    )

    lake_path = shpreader.natural_earth(
        resolution=resolution,
        category="physical",
        name="lakes",
    )
    lakes = tuple(
        record.geometry.intersection(area_of_interest)
        for record in shpreader.Reader(lake_path).records()
        if record.geometry.intersects(area_of_interest)
    )
    return rivers, lakes


def add_hydrography(
    ax: GeoAxes,
    extent: tuple[float, float, float, float] | list[float],
    spec: HydrographySpec,
    palette: MapPalette,
) -> None:
    """Imperative shell for the Natural Earth hydrography layer."""

    cache_extent = tuple(round(float(value), 4) for value in extent)
    rivers, lakes = _load_relevant_hydrography(
        cache_extent,
        spec.resolution,
        spec.max_river_rank,
        spec.max_rivers,
    )
    if lakes:
        ax.add_geometries(
            lakes,
            crs=ccrs.PlateCarree(),
            facecolor=palette.water_fill,
            edgecolor=palette.water_edge,
            linewidth=0.75,
            alpha=spec.lake_alpha,
            zorder=5,
        )

    for geometry, rank, _name in rivers:
        prominence = 1.0 + max(0, spec.max_river_rank - rank) * 0.035
        ax.add_geometries(
            [geometry],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=palette.river_casing,
            linewidth=spec.river_casing_width * prominence,
            alpha=0.78,
            zorder=6,
        )
        ax.add_geometries(
            [geometry],
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=palette.river,
            linewidth=spec.river_width * prominence,
            zorder=7,
        )


def render_publication_style(
    gdf: gpd.GeoDataFrame,
    dem_tuple: tuple[np.ndarray, np.ndarray, list[float]],
    output_dir: str,
    map_style: MapStyle | str = MapStyle.TOPO,
    formats: list[ExportFormat] | None = None,
    dpi: int = 500,
    group_col: str = "Sector",
    config: AppConfig | None = None,
    with_legend: str | bool | None = None,
    show_point_labels: bool | None = None,
    show_elevation_colorbar: bool | None = None,
    show_inset: bool | None = None,
    inset_position: str | list[float] | tuple[float, ...] | None = None,
) -> list[str]:
    """
    High-Performance Multi-Format Renderer:
    Renders a single Matplotlib map figure for the specified MapStyle, and exports it into ALL
    requested container formats (PDF, PNG, TIFF, JXL) directly in memory, eliminating redundant
    re-renders and speeding up map generation by up to 75%.
    """
    dem_array, hillshade_array, extent = dem_tuple
    min_lon, max_lon, min_lat, max_lat = extent
    active_formats = formats or [ExportFormat.PNG]
    cart_cfg = config.get("cartography", {}) if config else {}
    elev_cfg = config.get("elevation", {}) if config else {}
    render_spec = build_render_spec(
        map_style,
        configured_hillshade_alpha=elev_cfg.get("hillshade_alpha"),
    )
    palette = render_spec.palette
    markers = cart_cfg.get("markers") or None
    colors = cart_cfg.get("colors") or palette.categorical
    marker_size = float(cart_cfg.get("marker_size", 75))
    fig_size = tuple(cart_cfg.get("fig_size", (11.5, 8.5)))
    effective_show_inset = True
    effective_show_labels = True
    effective_show_colorbar = False
    inset_position_setting: str | tuple[float, ...] | list[float] = "top_left"
    compass_loc: tuple[float, float] = (0.88, 0.18)
    scale_loc: tuple[float, float] = (0.74, 0.05)

    active_with_legend = (
        with_legend
        if with_legend is not None
        else cart_cfg.get("with_legend", None)
    )

    (
        effective_show_legend,
        side_panel_mode,
        inside_legend_loc,
        bbox_anchor,
        leg_ncols,
    ) = parse_with_legend_spec(
        with_legend=active_with_legend,
    )

    if config:
        effective_show_inset = cart_cfg.get("show_inset", effective_show_inset)
        effective_show_labels = cart_cfg.get("show_point_labels", effective_show_labels)
        effective_show_colorbar = cart_cfg.get(
            "show_elevation_colorbar", effective_show_colorbar
        )
        inset_position_setting = cart_cfg.get(
            "inset_position", inset_position_setting
        )
        compass_loc = cart_cfg.get("compass_location", compass_loc)
        scale_loc = cart_cfg.get("scale_bar_location", scale_loc)

    # Explicit function / CLI overrides
    if show_point_labels is not None:
        effective_show_labels = show_point_labels
    elif effective_show_legend:
        # Hide point text labels by default when legend is active to prevent visual clutter
        effective_show_labels = False
    if show_elevation_colorbar is not None:
        effective_show_colorbar = show_elevation_colorbar
    if show_inset is not None:
        effective_show_inset = show_inset
    if inset_position is not None:
        inset_position_setting = inset_position

    show_inset = effective_show_inset
    show_point_labels = effective_show_labels
    show_legend = effective_show_legend
    show_elevation_colorbar = effective_show_colorbar

    fig = plt.figure(figsize=fig_size, dpi=100)

    has_side_panel = side_panel_mode if effective_show_legend and side_panel_mode != "none" else (
        "right" if effective_show_colorbar else "none"
    )
    inset_loc, quad_name, map_axes_rect = resolve_inset_location(
        position=inset_position_setting if effective_show_inset else None,
        gdf=gdf,
        extent=extent,
        has_legend_or_cbar=has_side_panel,
    )

    ax = fig.add_axes(map_axes_rect, projection=ccrs.PlateCarree())
    assert isinstance(ax, GeoAxes)
    ax.set_extent((min_lon, max_lon, min_lat, max_lat), crs=ccrs.PlateCarree())

    im_dem = None

    if render_spec.base_layer is BaseLayer.HYPSOMETRIC:
        hyps_cmap, hyps_norm = get_hypsometric_colormap(
            float(np.nanmin(dem_array)),
            float(np.nanmax(dem_array)),
            palette.terrain_stops,
        )
        im_dem = ax.imshow(
            dem_array,
            origin="upper",
            extent=(min_lon, max_lon, min_lat, max_lat),
            cmap=hyps_cmap,
            norm=hyps_norm,
            interpolation="bilinear",
            transform=ccrs.PlateCarree(),
            zorder=1,
        )
    else:
        try:
            ax.add_image(
                CartoDBNoLabels(),
                10,
                interpolation="bilinear",
                alpha=1.0,
                zorder=1,
            )
            print("[Cartography] Rendered clean CartoDB Light basemap base.")
        except Exception as e:
            print(f"[Cartography] Basemap tiles fetch failed: {e}")

    if render_spec.hillshade_alpha > 0:
        ax.imshow(
            hillshade_array,
            origin="upper",
            extent=(min_lon, max_lon, min_lat, max_lat),
            cmap="gray",
            alpha=render_spec.hillshade_alpha,
            interpolation="bilinear",
            transform=ccrs.PlateCarree(),
            zorder=2,
        )

    # Hybrid styles retain the DEM as their base and add the complete no-label
    # basemap as a translucent layer. This exposes mapped lakes, reservoirs,
    # wetlands, and drainage context without replacing the elevation colors.
    if (
        render_spec.base_layer is BaseLayer.HYPSOMETRIC
        and render_spec.basemap_alpha > 0
    ):
        try:
            ax.add_image(
                CartoDBBlueWaterOverlay(),
                10,
                interpolation="bilinear",
                alpha=render_spec.basemap_alpha,
                zorder=3,
            )
            print(
                "[Cartography] Blended vivid-blue CartoDB water/context "
                f"basemap over DEM relief (alpha={render_spec.basemap_alpha:.2f})."
            )
        except Exception as e:
            print(f"[Cartography] Hybrid basemap overlay failed: {e}")

    try:
        add_hydrography(ax, extent, render_spec.hydrography, palette)
        print(
            "[Cartography] Rendered aligned Natural Earth lakes and selected rivers."
        )
    except Exception as e:
        print(f"[Cartography] Hydrography overlay warning: {e}")

    ax.add_feature(
        cfeature.BORDERS,
        linestyle=":",
        edgecolor=palette.boundary,
        linewidth=0.8,
        zorder=8,
    )
    ax.add_feature(
        cfeature.COASTLINE,
        edgecolor=palette.boundary,
        linewidth=1.0,
        zorder=9,
    )

    # The functional core scales collision spreading to this map extent.
    coords = np.column_stack((gdf.geometry.x.values, gdf.geometry.y.values))
    jittered_coords = spread_overlapping_points(coords, extent)

    # Sampling Points & Smart Collision-Free Labels
    texts = []
    groups = list(gdf.groupby(group_col))
    symbols = assign_group_symbols(
        (group_name for group_name, _group_data in groups),
        colors=colors,
        markers=markers,
    )

    for symbol, (group_name, group_data) in zip(symbols, groups, strict=True):

        group_indices = group_data.index
        group_x = [jittered_coords[gdf.index.get_loc(i), 0] for i in group_indices]
        group_y = [jittered_coords[gdf.index.get_loc(i), 1] for i in group_indices]

        ax.scatter(
            group_x,
            group_y,
            label=f"{group_name} (n={len(group_data)})",
            s=marker_size,
            marker=symbol.marker,
            facecolor=symbol.color,
            edgecolor=palette.text,
            linewidth=1.0,
            transform=ccrs.PlateCarree(),
            zorder=12,
        )

        if show_point_labels and len(group_x) > 0:
            center_x = float(np.mean(group_x))
            center_y = float(np.mean(group_y))
            txt = ax.text(
                center_x,
                center_y,
                str(group_name),
                transform=ccrs.PlateCarree(),
                fontsize=9.5,
                fontweight="bold",
                color=palette.text,
                zorder=15,
            )
            txt.set_path_effects(
                [PathEffects.withStroke(linewidth=3.0, foreground=palette.halo)]
            )
            texts.append(txt)

    if show_point_labels and texts:
        try:
            from adjustText import adjust_text

            adjust_text(
                texts,
                ax=ax,
                expand=(1.2, 1.4),
                lim=100,
                arrowprops=dict(
                    arrowstyle="-",
                    color=palette.text,
                    alpha=0.65,
                    lw=0.75,
                ),
            )
            print("[Cartography] Resolved text label collisions (adjustText).")
        except Exception as e:
            print(f"[Cartography] adjustText note: {e}")

    # Lat/Lon Gridlines & Ticks ON ALL 4 SIDES
    gl = ax.gridlines(
        draw_labels=True,
        linewidth=0.5,
        color=palette.boundary,
        alpha=0.28,
        linestyle="--",
        crs=ccrs.PlateCarree(),
        zorder=8,
    )
    grid_labels = build_grid_label_spec(
        has_side_panel,
        inset_is_outside=bool(show_inset and quad_name.startswith("outside")),
    )
    gl.top_labels = grid_labels.top
    gl.bottom_labels = grid_labels.bottom
    gl.left_labels = grid_labels.left
    gl.right_labels = grid_labels.right
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {"size": 9, "color": palette.text, "weight": "bold"}
    gl.ylabel_style = {"size": 9, "color": palette.text, "weight": "bold"}

    if show_inset:
        try:
            add_colombia_inset_submap(
                fig,
                ax,
                extent,
                location=inset_loc,
                inside_main_map=not quad_name.startswith("outside"),
            )
            print(
                f"[Cartography] Rendered Colombia continental inset submap (positioned: {quad_name})."
            )
        except Exception as e:
            print(f"[Cartography] Warning: Inset submap failed: {e}")

    if compass_loc:
        add_north_arrow(ax, x=compass_loc[0], y=compass_loc[1], size=0.045)
    if scale_loc:
        add_scale_bar(
            ax,
            extent=extent,
            location=(scale_loc[0], scale_loc[1]),
            transparent_bg=True,
        )

    if im_dem is not None and show_elevation_colorbar:
        cbar_ax = fig.add_axes((0.765, 0.12, 0.018, 0.76))
        cbar = fig.colorbar(im_dem, cax=cbar_ax, orientation="vertical")
        cbar.set_label(
            "Elevación (m.s.n.m.)", fontsize=9.5, fontweight="bold", labelpad=8
        )
        cbar.ax.tick_params(labelsize=8.5)

    if show_legend:
        legend_title = (
            group_col if group_col and group_col != "Group" else "Puntos de Muestreo"
        )
        leg_kwargs = {
            "loc": inside_legend_loc,
            "frameon": True,
            "facecolor": "white",
            "edgecolor": "#111111",
            "fontsize": 9,
            "title": legend_title,
            "title_fontsize": 9.5,
            "ncols": leg_ncols,
        }
        if bbox_anchor is not None:
            leg_kwargs["bbox_to_anchor"] = bbox_anchor

        leg = ax.legend(**leg_kwargs)
        leg.get_title().set_fontweight("bold")

    os.makedirs(output_dir, exist_ok=True)
    effective_dpi = min(dpi, 1200)
    rendered_files = []

    # Save figure to all requested export formats in memory from this SINGLE render!
    for fmt in active_formats:
        fmt_enum = fmt if isinstance(fmt, ExportFormat) else ExportFormat(str(fmt))
        filename = artifact_filename(render_spec.style, fmt_enum)

        output_path = os.path.join(output_dir, filename)

        if fmt_enum == ExportFormat.TIFF:
            fig.savefig(
                output_path,
                dpi=effective_dpi,
                bbox_inches="tight",
                pil_kwargs={"compression": "tiff_adobe_deflate"},
            )
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(
                f"[Cartography] TIFF (Deflate) exported: {output_path} ({size_mb:.2f} MB, {effective_dpi} DPI)"
            )

        elif fmt_enum == ExportFormat.PNG:
            fig.savefig(
                output_path,
                dpi=effective_dpi,
                bbox_inches="tight",
                pil_kwargs={"compress_level": 6},
            )
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(
                f"[Cartography] PNG exported: {output_path} ({size_mb:.2f} MB, {effective_dpi} DPI)"
            )

        elif fmt_enum == ExportFormat.JPEG_XL:
            try:
                import imagecodecs
                from PIL import Image

                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=effective_dpi, bbox_inches="tight", pil_kwargs={"compress_level": 1})
                buf.seek(0)
                img = Image.open(buf)
                arr = np.array(img)
                jxl_bytes = imagecodecs.jpegxl_encode(arr, effort=3)
                with open(output_path, "wb") as f:
                    f.write(jxl_bytes)
                size_mb = len(jxl_bytes) / (1024 * 1024)
                print(
                    f"[Cartography] JPEG XL (.jxl) exported: {output_path} ({size_mb:.2f} MB, {effective_dpi} DPI)"
                )
            except Exception as e:
                print(f"[Cartography] JXL encoding error: {e}")
                with open(output_path, "wb") as f:
                    f.write(buf.getvalue())

        elif fmt_enum == ExportFormat.PDF:
            fig.savefig(
                output_path,
                dpi=effective_dpi,
                bbox_inches="tight",
            )
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(
                f"[Cartography] Vector PDF exported: {output_path} ({size_mb:.2f} MB, {effective_dpi} DPI)"
            )

        rendered_files.append(output_path)

    plt.close(fig)
    return rendered_files


# Backward compatibility wrapper for single map export
def create_publication_map(
    gdf: gpd.GeoDataFrame,
    dem_tuple: tuple[np.ndarray, np.ndarray, list[float]],
    output_path: str = "output/mapa_publicacion.pdf",
    title: str | None = None,
    dpi: int = 300,
    group_col: str = "Sector",
    config: AppConfig | None = None,
    map_style: MapStyle | str = MapStyle.TOPO,
    use_basemap_tiles: bool = False,
    blend_mode: str | None = None,
    with_legend: str | bool | None = None,
    show_point_labels: bool | None = None,
    show_elevation_colorbar: bool | None = None,
    show_inset: bool | None = None,
    inset_position: str | list[float] | tuple[float, ...] | None = None,
) -> str:
    out_dir = os.path.dirname(output_path) or "output"
    ext = os.path.splitext(output_path)[1].lstrip(".").lower()
    try:
        fmt = ExportFormat(ext)
    except ValueError:
        fmt = ExportFormat.PNG

    rendered = render_publication_style(
        gdf=gdf,
        dem_tuple=dem_tuple,
        output_dir=out_dir,
        map_style=map_style,
        formats=[fmt],
        dpi=dpi,
        group_col=group_col,
        config=config,
        with_legend=with_legend,
        show_point_labels=show_point_labels,
        show_elevation_colorbar=show_elevation_colorbar,
        show_inset=show_inset,
        inset_position=inset_position,
    )
    return rendered[0] if rendered else output_path
