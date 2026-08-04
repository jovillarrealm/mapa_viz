"""Lifecycle helpers for generated map artifacts."""

import os
import shutil


_LEGACY_ROOT_ARTIFACTS = {
    "mapa_publicacion.jxl",
    "mapa_publicacion.pdf",
    "mapa_publicacion.png",
    "mapa_publicacion.tif",
    "mapa_publicacion.tiff",
}


def prepare_dataset_output_directory(
    output_dir: str, *, replace_existing: bool
) -> None:
    """Create a clean directory for one dataset's generated artifacts."""
    if replace_existing and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)


def remove_legacy_root_artifacts(base_output_dir: str) -> list[str]:
    """Remove root-level publication copies created by older pipeline versions."""
    if not os.path.isdir(base_output_dir):
        return []

    removed: list[str] = []
    with os.scandir(base_output_dir) as entries:
        for entry in entries:
            if entry.name in _LEGACY_ROOT_ARTIFACTS and entry.is_file():
                os.remove(entry.path)
                removed.append(entry.path)
    return removed
