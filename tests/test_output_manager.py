from pathlib import Path

import pytest

from core.output_manager import (
    missing_artifacts,
    prepare_dataset_output_directory,
    remove_legacy_root_artifacts,
    staged_dataset_output_directory,
)


def test_prepare_dataset_output_directory_replaces_previous_run(tmp_path):
    output_dir = tmp_path / "output" / "dataset"
    nested_dir = output_dir / "old"
    nested_dir.mkdir(parents=True)
    (output_dir / "mapa_publicacion.pdf").write_text("stale", encoding="utf-8")
    (nested_dir / "partial.png").write_text("stale", encoding="utf-8")

    prepare_dataset_output_directory(str(output_dir), replace_existing=True)

    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []


def test_prepare_dataset_output_directory_preserves_timestamped_run(tmp_path):
    output_dir = tmp_path / "output" / "dataset_20260804_120000"
    output_dir.mkdir(parents=True)
    artifact = output_dir / "mapa_publicacion.pdf"
    artifact.write_text("current", encoding="utf-8")

    prepare_dataset_output_directory(str(output_dir), replace_existing=False)

    assert artifact.read_text(encoding="utf-8") == "current"


def test_remove_legacy_root_artifacts_leaves_dataset_outputs_untouched(tmp_path):
    output_dir = tmp_path / "output"
    dataset_dir = output_dir / "Liseth"
    dataset_dir.mkdir(parents=True)
    legacy_png = output_dir / "mapa_publicacion.png"
    legacy_pdf = output_dir / "mapa_publicacion.pdf"
    unrelated = output_dir / "notes.txt"
    dataset_artifact = dataset_dir / "mapa_publicacion.png"
    for path in (legacy_png, legacy_pdf, unrelated, dataset_artifact):
        path.write_text("content", encoding="utf-8")

    removed = remove_legacy_root_artifacts(str(output_dir))

    assert set(removed) == {str(legacy_png), str(legacy_pdf)}
    assert not legacy_png.exists()
    assert not legacy_pdf.exists()
    assert unrelated.exists()
    assert dataset_artifact.exists()


def test_staged_output_replaces_dataset_only_after_success(tmp_path):
    output_dir = tmp_path / "output" / "dataset"
    output_dir.mkdir(parents=True)
    (output_dir / "mapa_publicacion.png").write_text("old", encoding="utf-8")

    with staged_dataset_output_directory(
        str(output_dir), replace_existing=True
    ) as staging_dir:
        staged_artifact = Path(staging_dir) / "mapa_publicacion.png"
        staged_artifact.write_text("new", encoding="utf-8")
        assert (output_dir / "mapa_publicacion.png").read_text(
            encoding="utf-8"
        ) == "old"

    assert (output_dir / "mapa_publicacion.png").read_text(encoding="utf-8") == "new"


def test_staged_output_rolls_back_when_rendering_fails(tmp_path):
    output_dir = tmp_path / "output" / "dataset"
    output_dir.mkdir(parents=True)
    artifact = output_dir / "mapa_publicacion.png"
    artifact.write_text("last-good", encoding="utf-8")

    with pytest.raises(RuntimeError, match="render failed"):
        with staged_dataset_output_directory(
            str(output_dir), replace_existing=True
        ) as staging_dir:
            (Path(staging_dir) / "partial.png").write_text("partial", encoding="utf-8")
            raise RuntimeError("render failed")

    assert artifact.read_text(encoding="utf-8") == "last-good"
    assert not list((tmp_path / "output").glob(".dataset.staging-*"))


def test_missing_artifacts_reports_the_unfulfilled_plan(tmp_path):
    (tmp_path / "mapa_publicacion.png").write_text("ok", encoding="utf-8")

    assert missing_artifacts(
        str(tmp_path),
        ("mapa_publicacion.png", "mapa_interactivo.html"),
    ) == ("mapa_interactivo.html",)
