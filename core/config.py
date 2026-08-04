"""Validated application configuration types.

YAML is an untyped boundary. This module narrows it once into explicit
``TypedDict`` contracts so rendering code never needs a dynamic value type.
"""

from collections.abc import Mapping
from typing import TypedDict


class IngestionConfig(TypedDict, total=False):
    lat_candidates: tuple[str, ...]
    lon_candidates: tuple[str, ...]
    default_crs: str


class ElevationConfig(TypedDict, total=False):
    padding_deg: float
    resolution_arcsec: int
    azimuth_deg: float
    altitude_deg: float
    hillshade_alpha: float
    hypsometric_cmap: str


class CartographyConfig(TypedDict, total=False):
    output_dpi: int
    fig_size: tuple[float, float]
    font_family: str
    grid_line_style: str
    grid_alpha: float
    marker_size: float
    show_inset: bool
    inset_position: str | tuple[float, float, float, float]
    show_compass: bool
    compass_location: tuple[float, float]
    show_scale_bar: bool
    scale_bar_location: tuple[float, float]
    show_point_labels: bool
    show_legend: bool
    show_elevation_colorbar: bool
    markers: tuple[str, ...]
    colors: tuple[str, ...]
    rivers_scale: str
    lakes_scale: str


class WebMapConfig(TypedDict, total=False):
    default_zoom: int
    tiles: str


class AppConfig(TypedDict, total=False):
    ingestion: IngestionConfig
    elevation: ElevationConfig
    cartography: CartographyConfig
    web_map: WebMapConfig


def _string_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str)
    }


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(item for item in value if isinstance(item, str))


def _float_tuple(value: object, length: int) -> tuple[float, ...] | None:
    if not isinstance(value, list) or len(value) != length:
        return None
    parsed = tuple(_float(item) for item in value)
    if any(item is None for item in parsed):
        return None
    return tuple(float(item) for item in parsed if item is not None)


def parse_config(raw: object) -> AppConfig:
    """Validate a YAML object into the application's closed configuration schema."""

    root = _string_mapping(raw)
    result: AppConfig = {}

    ingestion_raw = _string_mapping(root.get("ingestion"))
    ingestion: IngestionConfig = {}
    if (value := _strings(ingestion_raw.get("lat_candidates"))) is not None:
        ingestion["lat_candidates"] = value
    if (value := _strings(ingestion_raw.get("lon_candidates"))) is not None:
        ingestion["lon_candidates"] = value
    if (value := _string(ingestion_raw.get("default_crs"))) is not None:
        ingestion["default_crs"] = value
    if ingestion:
        result["ingestion"] = ingestion

    elevation_raw = _string_mapping(root.get("elevation"))
    elevation: ElevationConfig = {}
    if (value := _float(elevation_raw.get("padding_deg"))) is not None:
        elevation["padding_deg"] = value
    if (value := _float(elevation_raw.get("azimuth_deg"))) is not None:
        elevation["azimuth_deg"] = value
    if (value := _float(elevation_raw.get("altitude_deg"))) is not None:
        elevation["altitude_deg"] = value
    if (value := _float(elevation_raw.get("hillshade_alpha"))) is not None:
        elevation["hillshade_alpha"] = value
    if (value := _integer(elevation_raw.get("resolution_arcsec"))) is not None:
        elevation["resolution_arcsec"] = value
    if (value := _string(elevation_raw.get("hypsometric_cmap"))) is not None:
        elevation["hypsometric_cmap"] = value
    if elevation:
        result["elevation"] = elevation

    cartography_raw = _string_mapping(root.get("cartography"))
    cartography: CartographyConfig = {}
    if (value := _integer(cartography_raw.get("output_dpi"))) is not None:
        cartography["output_dpi"] = value
    if (value := _float_tuple(cartography_raw.get("fig_size"), 2)) is not None:
        cartography["fig_size"] = (value[0], value[1])
    if (value := _string(cartography_raw.get("font_family"))) is not None:
        cartography["font_family"] = value
    if (value := _string(cartography_raw.get("grid_line_style"))) is not None:
        cartography["grid_line_style"] = value
    if (value := _string(cartography_raw.get("rivers_scale"))) is not None:
        cartography["rivers_scale"] = value
    if (value := _string(cartography_raw.get("lakes_scale"))) is not None:
        cartography["lakes_scale"] = value
    if (value := _float(cartography_raw.get("grid_alpha"))) is not None:
        cartography["grid_alpha"] = value
    if (value := _float(cartography_raw.get("marker_size"))) is not None:
        cartography["marker_size"] = value
    if (value := _boolean(cartography_raw.get("show_inset"))) is not None:
        cartography["show_inset"] = value
    if (value := _boolean(cartography_raw.get("show_compass"))) is not None:
        cartography["show_compass"] = value
    if (value := _boolean(cartography_raw.get("show_scale_bar"))) is not None:
        cartography["show_scale_bar"] = value
    if (value := _boolean(cartography_raw.get("show_point_labels"))) is not None:
        cartography["show_point_labels"] = value
    if (value := _boolean(cartography_raw.get("show_legend"))) is not None:
        cartography["show_legend"] = value
    if (value := _boolean(cartography_raw.get("show_elevation_colorbar"))) is not None:
        cartography["show_elevation_colorbar"] = value
    inset_raw = cartography_raw.get("inset_position")
    if (value := _string(inset_raw)) is not None:
        cartography["inset_position"] = value
    elif (value := _float_tuple(inset_raw, 4)) is not None:
        cartography["inset_position"] = (value[0], value[1], value[2], value[3])
    if (value := _float_tuple(cartography_raw.get("compass_location"), 2)) is not None:
        cartography["compass_location"] = (value[0], value[1])
    if (value := _float_tuple(cartography_raw.get("scale_bar_location"), 2)) is not None:
        cartography["scale_bar_location"] = (value[0], value[1])
    if (value := _strings(cartography_raw.get("markers"))) is not None:
        cartography["markers"] = value
    if (value := _strings(cartography_raw.get("colors"))) is not None:
        cartography["colors"] = value
    if cartography:
        result["cartography"] = cartography

    web_raw = _string_mapping(root.get("web_map"))
    web_map: WebMapConfig = {}
    if (value := _integer(web_raw.get("default_zoom"))) is not None:
        web_map["default_zoom"] = value
    if (value := _string(web_raw.get("tiles"))) is not None:
        web_map["tiles"] = value
    if web_map:
        result["web_map"] = web_map

    return result
