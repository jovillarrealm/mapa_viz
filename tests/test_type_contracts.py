import ast
from pathlib import Path

import pandas as pd

from core.adapters.registry import load_dataset
from core.config import parse_config
from core.result import Err


def test_yaml_configuration_is_narrowed_to_typed_values():
    config = parse_config(
        {
            "elevation": {"hillshade_alpha": 0.25, "resolution_arcsec": "bad"},
            "cartography": {
                "fig_size": [11.5, 8.5],
                "show_inset": True,
                "colors": ["#0067B1", "#E64B35"],
                "marker_size": "large",
            },
        }
    )

    assert config["elevation"]["hillshade_alpha"] == 0.25
    assert "resolution_arcsec" not in config["elevation"]
    assert config["cartography"]["fig_size"] == (11.5, 8.5)
    assert config["cartography"]["colors"] == ("#0067B1", "#E64B35")
    assert "marker_size" not in config["cartography"]


def test_in_memory_dataframe_is_a_typed_adapter_source():
    frame = pd.DataFrame(
        {
            "Sector": ["S1", "S2"],
            "Latitude": [6.2, 6.4],
            "Longitude": [-75.2, -75.0],
        }
    )

    result = load_dataset(frame)

    if isinstance(result, Err):
        raise AssertionError(result.error)
    assert result.value.num_points == 2
    assert result.value.source_path == "DataFrame"


def test_application_source_has_no_banned_dynamic_type_nodes():
    project_root = Path(__file__).resolve().parents[1]
    source_files = [project_root / "main.py", *sorted((project_root / "core").rglob("*.py"))]
    violations: list[str] = []

    for source_file in source_files:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(f"{source_file}:{node.lineno}")
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "Any":
                        violations.append(f"{source_file}:{node.lineno}")

    assert not violations, f"Banned dynamic type found at: {violations}"
