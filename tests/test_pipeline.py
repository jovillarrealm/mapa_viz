from dataclasses import replace
import os

from core.domain import ExportFormat, MapStyle
from core.pipeline import (
    CartographyOverrides,
    artifact_filename,
    dataset_output_directory,
    resolve_render_selection,
)


def test_render_selection_resolves_aliases_and_deduplicates_stably():
    selection = resolve_render_selection(
        ["TOPO", "topographic", "publication"],
        ["png", "PNG", "web"],
        include_web_map=False,
    )

    assert selection.styles == (MapStyle.TOPO, MapStyle.HYBRID_AQUATIC)
    assert selection.formats == (ExportFormat.PNG,)
    assert selection.include_web_map is True
    assert selection.expected_artifact_names == (
        "mapa_topologico.png",
        "mapa_publicacion.png",
        "mapa_interactivo.html",
    )


def test_all_render_selection_preserves_the_public_output_contract():
    selection = resolve_render_selection(["all"], ["all"], include_web_map=True)

    assert len(selection.styles) == 3
    assert len(selection.formats) == 4
    assert len(selection.expected_artifact_names) == 13
    assert (
        artifact_filename(MapStyle.BASEMAP, ExportFormat.JPEG_XL) == "mapa_basemap.jxl"
    )


def test_pipeline_values_are_immutable_and_paths_are_clock_independent():
    overrides = CartographyOverrides(show_inset=True)
    updated = replace(overrides, show_inset=False)

    assert overrides.show_inset is True
    assert updated.show_inset is False

    assert dataset_output_directory(
        "output",
        "SampleSites",
        unique_dirs=True,
        timestamp="20260806_120000",
    ) == os.path.join("output", "SampleSites_20260806_120000")
