from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image
from shapely.geometry import LineString, box

from core import cartography


@pytest.mark.parametrize("style", ["topo", "hybrid_aquatic", "publicacion", "basemap"])
def test_render_preserves_water_layer_and_authenticates_tiles(
    tmp_path, monkeypatch, style
):
    monkeypatch.setenv("CARTO_BASEMAP_API_KEY", "test-key")
    extent = [-76.0, -75.0, 6.0, 7.0]
    points = np.array([[-75.8, 6.2], [-75.2, 6.8]])
    gdf = gpd.GeoDataFrame(
        {"Sector": ["A", "B"]},
        geometry=gpd.points_from_xy(*points.T),
        crs="EPSG:4326",
    )
    dem = np.arange(16, dtype=float).reshape(4, 4)
    river = LineString([(-75.9, 6.1), (-75.5, 6.5), (-75.1, 6.9)])
    lake = box(-75.7, 6.4, -75.6, 6.5)
    empty_feature = cfeature.ShapelyFeature([], ccrs.PlateCarree())
    # Keep the real renderer and vector drawing; replace external data only.
    with (
        patch.object(
            cartography,
            "_load_relevant_hydrography",
            return_value=(((river, 1, "River"),), (lake,)),
        ),
        patch.object(cfeature, "BORDERS", empty_feature),
        patch.object(cfeature, "COASTLINE", empty_feature),
        patch.object(
            cartography.CartoDBNoLabels,
            "image_for_domain",
            return_value=(
                np.full((2, 2, 3), 255, dtype=np.uint8),
                (-9e6, -8e6, 6e5, 9e5),
                "lower",
            ),
        ),
        patch.object(plt, "close") as close,
    ):
        files = cartography.render_publication_style(
            gdf,
            (dem, np.full_like(dem, 0.5), extent),
            str(tmp_path),
            map_style=style,
            dpi=40,
            show_inset=False,
            show_point_labels=False,
        )
        figure = close.call_args.args[0]

    try:
        ax = figure.axes[0]
        assert len(ax.img_factories) == (0 if style == "topo" else 1)
        if style != "topo":
            source = ax.img_factories[0][0]
            assert parse_qs(urlparse(source._image_url((300, 493, 10))).query) == {
                "key": ["test-key"]
            }
            assert any("© CARTO" in text.get_text() for text in ax.texts)
        assert [
            tuple(artist._feature.geometries()) for artist in ax.collections[:3]
        ] == [(lake,), (river,), (river,)]
        np.testing.assert_allclose(ax.get_extent(), extent)
        np.testing.assert_allclose(
            np.concatenate([artist.get_offsets() for artist in ax.collections[-2:]]),
            points,
        )
        if style != "basemap":
            np.testing.assert_array_equal(ax.images[0].get_array(), dem)
            assert len(ax.images) == (2 if style == "topo" else 3)
        assert len(files) == 1
        assert (tmp_path / files[0]).is_file()
    finally:
        plt.close(figure)


def test_carto_requires_key_before_requesting_watermarked_tiles(monkeypatch):
    monkeypatch.delenv("CARTO_BASEMAP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="CARTO_BASEMAP_API_KEY"):
        cartography.CartoDBNoLabels()


def test_carto_encodes_the_key_in_tile_requests(monkeypatch):
    monkeypatch.setenv("CARTO_BASEMAP_API_KEY", "test+key&value=1")
    url = urlparse(cartography.CartoDBNoLabels()._image_url((300, 493, 10)))
    assert url.scheme == "https"
    assert url.path.endswith("/light_nolabels/10/300/493.png")
    assert parse_qs(url.query) == {"key": ["test+key&value=1"]}


def test_water_overlay_retains_water_detail(monkeypatch):
    monkeypatch.setenv("CARTO_BASEMAP_API_KEY", "test-key")
    tile = Image.new("RGB", (2, 1))
    tile.putdata([(250, 250, 248), (210, 219, 222)])
    extent = (0.0, 1.0, 0.0, 1.0)
    with patch.object(
        cartography.cimgt.GoogleWTS, "get_image", return_value=(tile, extent, "lower")
    ):
        styled, bounds, origin = cartography.CartoDBBlueWaterOverlay().get_image(
            (0, 0, 0)
        )
    assert styled.getpixel((0, 0)) == (250, 250, 248, 70)
    assert styled.getpixel((1, 0)) == (0, 119, 182, 235)
    assert (bounds, origin) == (extent, "lower")


@pytest.mark.parametrize("style", ["hybrid_aquatic", "basemap"])
def test_missing_key_keeps_previous_output(tmp_path, monkeypatch, style):
    monkeypatch.delenv("CARTO_BASEMAP_API_KEY", raising=False)
    filename = (
        "mapa_publicacion.png" if style == "hybrid_aquatic" else "mapa_basemap.png"
    )
    previous = tmp_path / filename
    previous.write_bytes(b"previous complete map")
    with patch.object(plt, "figure") as figure:
        with pytest.raises(ValueError, match="CARTO_BASEMAP_API_KEY"):
            cartography.render_publication_style(
                gpd.GeoDataFrame(),
                (np.zeros((2, 2)), np.zeros((2, 2)), [-76.0, -75.0, 6.0, 7.0]),
                str(tmp_path),
                map_style=style,
            )
        figure.assert_not_called()
    assert previous.read_bytes() == b"previous complete map"
