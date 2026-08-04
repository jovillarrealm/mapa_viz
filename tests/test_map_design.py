import numpy as np
from PIL import Image

from core.cartography import colorize_hybrid_basemap
from core.domain import MapStyle
from core.map_design import (
    BaseLayer,
    PUBLICATION_CATEGORICAL,
    assign_group_symbols,
    build_render_spec,
    spread_overlapping_points,
)


def test_publication_and_hybrid_layer_specs_are_explicit():
    publication = build_render_spec("publicacion")
    aquatic = build_render_spec(MapStyle.HYBRID_AQUATIC)
    relief = build_render_spec(MapStyle.HYBRID_RELIEF)

    assert publication.style is MapStyle.TOPO
    assert publication.base_layer is BaseLayer.HYPSOMETRIC
    assert aquatic.base_layer is BaseLayer.HYPSOMETRIC
    assert aquatic.hydrography.river_width > publication.hydrography.river_width
    assert relief.base_layer is BaseLayer.HYPSOMETRIC
    assert aquatic.basemap_alpha > relief.basemap_alpha > 0
    assert relief.hillshade_alpha > aquatic.hillshade_alpha


def test_group_symbols_are_stable_and_use_publication_palette():
    symbols = assign_group_symbols(["S1", "S2", "S3"])

    assert [symbol.group for symbol in symbols] == ["S1", "S2", "S3"]
    assert [symbol.color for symbol in symbols] == list(PUBLICATION_CATEGORICAL[:3])
    assert len({symbol.marker for symbol in symbols}) == 3


def test_spread_overlapping_points_is_pure_and_extent_scaled():
    coordinates = np.array([[0.5, 0.5], [0.5, 0.5], [0.9, 0.9]])
    original = coordinates.copy()

    spread = spread_overlapping_points(coordinates, [0.0, 1.0, 0.0, 1.0])

    assert np.array_equal(coordinates, original)
    assert not np.array_equal(spread[0], spread[1])
    assert np.array_equal(spread[2], coordinates[2])


def test_hybrid_basemap_makes_water_blue_and_context_translucent():
    tile = Image.new("RGBA", (2, 1))
    tile.putdata([(250, 250, 248, 255), (210, 219, 222, 255)])

    styled = colorize_hybrid_basemap(tile)

    assert styled.getpixel((0, 0)) == (250, 250, 248, 70)
    assert styled.getpixel((1, 0)) == (0, 119, 182, 235)
