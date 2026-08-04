from core.output_manager import (
    prepare_dataset_output_directory,
    remove_legacy_root_artifacts,
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
