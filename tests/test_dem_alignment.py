import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from core.dem_handler import compute_hillshade, merge_dem_tiles_to_wgs84


def test_merge_dem_tiles_crops_to_requested_wgs84_bounds():
    source = np.arange(100, dtype=np.float32).reshape(10, 10)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_bounds(0, 0, 10, 10, 10, 10),
        ) as dataset:
            dataset.write(source, 1)
        with memory.open() as dataset:
            cropped = merge_dem_tiles_to_wgs84([dataset], (2, 2, 8, 8))

    assert cropped.shape == (6, 6)
    assert cropped.min() >= source.min()
    assert cropped.max() <= source.max()


def test_compute_hillshade_uses_map_scale_and_stays_finite():
    dem = np.tile(np.linspace(0, 1000, 100), (80, 1)).astype(np.float32)
    hillshade = compute_hillshade(dem, [-76.0, -75.0, 6.0, 7.0])

    assert hillshade.shape == dem.shape
    assert np.isfinite(hillshade).all()
    assert 0.0 <= hillshade.min() <= hillshade.max() <= 1.0
