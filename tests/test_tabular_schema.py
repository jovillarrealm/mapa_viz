import pandas as pd

from core.tabular_schema import detect_lat_lon_columns, ensure_group_column


def test_schema_inference_is_shared_and_does_not_mutate_ungrouped_input():
    frame = pd.DataFrame({"Latitud": [6.2], "Longitud": [-75.5]})

    assert detect_lat_lon_columns(frame) == ("Latitud", "Longitud")
    normalized, group_col = ensure_group_column(frame)

    assert group_col == "Group"
    assert "Group" not in frame.columns
    assert normalized["Group"].tolist() == ["Puntos de Muestreo"]
