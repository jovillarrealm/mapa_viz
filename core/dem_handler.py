import io
import math
from contextlib import ExitStack
from functools import lru_cache

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from matplotlib.colors import LightSource
from rasterio.merge import merge
from rasterio.vrt import WarpedVRT
from requests.adapters import HTTPAdapter
from scipy.ndimage import gaussian_filter

_HTTP_SESSION: requests.Session | None = None


def get_http_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        _HTTP_SESSION.mount("https://", adapter)
        _HTTP_SESSION.mount("http://", adapter)
    return _HTTP_SESSION


def compute_bounding_box(
    gdf: gpd.GeoDataFrame, padding: float = 0.35
) -> tuple[float, float, float, float]:
    """
    Computes dynamic bounding box [min_lon, min_lat, max_lon, max_lat] with specified padding.
    """
    total_bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    min_lon = float(total_bounds[0] - padding)
    min_lat = float(total_bounds[1] - padding)
    max_lon = float(total_bounds[2] + padding)
    max_lat = float(total_bounds[3] + padding)
    return min_lon, min_lat, max_lon, max_lat


def latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


@lru_cache(maxsize=128)
def fetch_tile_bytes(x: int, y: int, zoom: int) -> bytes | None:
    session = get_http_session()
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{zoom}/{x}/{y}.tif"
    for _attempt in range(3):
        try:
            resp = session.get(url, timeout=3.5)
            if resp.status_code == 200 and len(resp.content) > 500:
                return resp.content
        except Exception:
            pass
    return None


def fetch_single_tile(x: int, y: int, zoom: int) -> rasterio.DatasetReader | None:
    b = fetch_tile_bytes(x, y, zoom)
    if b:
        return rasterio.open(io.BytesIO(b))
    return None


def merge_dem_tiles_to_wgs84(
    datasets: list[rasterio.DatasetReader],
    bounds_wgs84: tuple[float, float, float, float],
) -> np.ndarray:
    """Reproject and crop source DEM tiles to the exact WGS84 map bounds.

    AWS elevation tiles are Web Mercator rasters.  Treating their complete tile
    mosaics as if they already occupied the requested latitude/longitude bounds
    stretches the terrain and breaks alignment with vector layers.  Warped VRTs
    preserve the source georeferencing and let Rasterio crop after reprojection.
    """

    if not datasets:
        raise ValueError("At least one DEM dataset is required")

    min_lon, min_lat, max_lon, max_lat = bounds_wgs84
    with ExitStack() as stack:
        warped = [
            stack.enter_context(
                WarpedVRT(
                    dataset,
                    crs="EPSG:4326",
                    resampling=Resampling.bilinear,
                )
            )
            for dataset in datasets
        ]
        mosaic, _transform = merge(
            warped,
            bounds=(min_lon, min_lat, max_lon, max_lat),
            resampling=Resampling.bilinear,
        )
    return mosaic[0].astype(np.float32)


def clean_dem_array(elevation: np.ndarray) -> np.ndarray:
    """Return a finite DEM with nodata holes interpolated from nearest terrain."""

    cleaned = np.asarray(elevation, dtype=np.float32).copy()
    nodata_mask = (cleaned <= -400.0) | ~np.isfinite(cleaned)
    if np.any(nodata_mask) and np.any(~nodata_mask):
        from scipy.ndimage import distance_transform_edt

        indices = distance_transform_edt(
            nodata_mask, return_distances=False, return_indices=True
        )
        nearest = cleaned[tuple(indices)]
        smooth = gaussian_filter(nearest, sigma=3.0)
        cleaned[nodata_mask] = smooth[nodata_mask]
    return cleaned


def fetch_aws_dem_tiles(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int = 9
) -> tuple[np.ndarray | None, bool]:
    """
    Fetches real DEM elevation tiles from AWS Open Data in parallel using persistent HTTP sessions,
    merges them into a single seamless elevation array, and clips to the bounding box.
    """
    from concurrent.futures import ThreadPoolExecutor

    try:
        x_min, y_max = latlon_to_tile(min_lat, min_lon, zoom)
        x_max, y_min = latlon_to_tile(max_lat, max_lon, zoom)

        if (x_max - x_min + 1) * (y_max - y_min + 1) > 36:
            zoom = max(6, zoom - 1)
            x_min, y_max = latlon_to_tile(min_lat, min_lon, zoom)
            x_max, y_min = latlon_to_tile(max_lat, max_lon, zoom)

        print(
            f"[DEM] Fetching AWS DEM elevation tiles for bounding box at zoom {zoom}..."
        )
        tiles_to_fetch = [
            (x, y, zoom)
            for x in range(x_min, x_max + 1)
            for y in range(y_min, y_max + 1)
        ]

        datasets: list[rasterio.DatasetReader] = []
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = executor.map(
                lambda t: fetch_single_tile(t[0], t[1], t[2]), tiles_to_fetch
            )
            datasets = [ds for ds in results if ds is not None]

        try:
            if datasets:
                elev_data = merge_dem_tiles_to_wgs84(
                    datasets,
                    (min_lon, min_lat, max_lon, max_lat),
                )
                elev_data = clean_dem_array(elev_data)

                print(
                    "[DEM] Real DEM reprojected, cropped, and cleaned successfully: "
                    f"shape={elev_data.shape}, min={elev_data.min():.1f}m, "
                    f"max={elev_data.max():.1f}m"
                )
                return elev_data, True
        finally:
            for dataset in datasets:
                dataset.close()
    except Exception as e:
        print(f"[DEM] AWS DEM fetch failed: {e}")
    return None, False


def generate_procedural_dem(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, grid_size: int = 300
) -> np.ndarray:
    """
    Fallback: Generates a realistic topographical DEM mesh matching the geographic coordinates.
    """
    x = np.linspace(min_lon, max_lon, grid_size)
    y = np.linspace(min_lat, max_lat, grid_size)
    xx, yy = np.meshgrid(x, y)

    base = 200 + 350 * np.sin(xx * 2.5) + 280 * np.cos(yy * 2.5)
    ridges = 450 * np.abs(np.sin(xx * 5.0 + yy * 3.0)) + 350 * np.exp(
        -((xx - (min_lon + max_lon) / 2) ** 2 + (yy - (min_lat + max_lat) / 2) ** 2)
        / 0.05
    )
    river_valley = -300 * np.exp(
        -((yy - (min_lat + 0.3 * (max_lat - min_lat) + 0.2 * np.sin(xx * 8))) ** 2)
        / 0.005
    )

    dem = base + ridges + river_valley
    dem = gaussian_filter(dem, sigma=2.5)
    dem = np.clip(dem, -250, 4500)
    return dem


def compute_hillshade(
    dem_array: np.ndarray,
    extent: tuple[float, float, float, float] | list[float],
    *,
    azimuth: float = 315.0,
    altitude: float = 45.0,
    smoothing_sigma: float = 0.8,
) -> np.ndarray:
    """Compute physically scaled relief from a north-up WGS84 elevation grid."""

    min_lon, max_lon, min_lat, max_lat = (float(v) for v in extent)
    rows, columns = dem_array.shape
    center_lat = (min_lat + max_lat) / 2.0
    dx_m = max(
        1.0,
        (max_lon - min_lon) * 111_320.0 * math.cos(math.radians(center_lat))
        / max(columns, 1),
    )
    dy_m = max(1.0, (max_lat - min_lat) * 110_574.0 / max(rows, 1))
    smoothed = gaussian_filter(
        np.asarray(dem_array, dtype=np.float32), sigma=smoothing_sigma
    )
    light = LightSource(azdeg=azimuth, altdeg=altitude)
    return light.hillshade(
        smoothed,
        vert_exag=1.0,
        dx=dx_m,
        dy=dy_m,
    ).astype(np.float32)


def get_dem_and_hillshade(
    gdf: gpd.GeoDataFrame,
    padding: float = 0.35,
    azimuth: float = 315.0,
    altitude: float = 45.0,
    zoom: int = 9,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """
    Obtains real global elevation DEM and computes 3D Hillshade relief.
    Returns (dem_array, hillshade_array, extent=[min_lon, max_lon, min_lat, max_lat]).
    """
    min_lon, min_lat, max_lon, max_lat = compute_bounding_box(gdf, padding=padding)
    extent = [min_lon, max_lon, min_lat, max_lat]

    # Fetch real AWS DEM tiles
    dem_array, success = fetch_aws_dem_tiles(
        min_lon, min_lat, max_lon, max_lat, zoom=zoom
    )

    if not success or dem_array is None:
        print(
            "[DEM] Using procedural topographic DEM fallback for 3D hillshade blend..."
        )
        dem_array = generate_procedural_dem(
            min_lon, min_lat, max_lon, max_lat, grid_size=400
        )

    # Physical pixel spacing avoids the over-exaggerated, noisy relief produced
    # by treating every raster cell as one metre wide.
    hillshade_array = compute_hillshade(
        dem_array,
        extent,
        azimuth=azimuth,
        altitude=altitude,
    )

    return dem_array, hillshade_array, extent
