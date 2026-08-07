"""Lifecycle helpers for generated map artifacts."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
import shutil
import tempfile


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


@contextmanager
def staged_dataset_output_directory(
    output_dir: str, *, replace_existing: bool
) -> Iterator[str]:
    """Publish a complete dataset directory, preserving the old one on failure.

    Renderers write into a sibling staging directory.  Only a successful context
    replaces the public dataset directory, so partial runs are never exposed.
    """

    final_path = os.path.abspath(output_dir)
    parent_dir = os.path.dirname(final_path)
    dataset_name = os.path.basename(final_path)
    os.makedirs(parent_dir, exist_ok=True)

    staging_path = tempfile.mkdtemp(prefix=f".{dataset_name}.staging-", dir=parent_dir)
    previous_path: str | None = None

    try:
        yield staging_path

        if os.path.exists(final_path):
            if not replace_existing:
                raise FileExistsError(f"Output directory already exists: {final_path}")
            previous_path = tempfile.mkdtemp(
                prefix=f".{dataset_name}.previous-", dir=parent_dir
            )
            os.rmdir(previous_path)
            os.replace(final_path, previous_path)

        try:
            os.replace(staging_path, final_path)
        except Exception:
            if previous_path is not None and os.path.exists(previous_path):
                os.replace(previous_path, final_path)
            raise

        if previous_path is not None:
            # Publication already succeeded; cleanup must not turn it into a
            # reported render failure (for example because an antivirus briefly
            # holds a handle on Windows).
            shutil.rmtree(previous_path, ignore_errors=True)
    except Exception:
        if os.path.isdir(staging_path):
            shutil.rmtree(staging_path, ignore_errors=True)
        raise


def missing_artifacts(
    output_dir: str, expected_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Return planned artifacts that were not produced by the imperative shell."""

    return tuple(
        name
        for name in expected_names
        if not os.path.isfile(os.path.join(output_dir, name))
    )


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
