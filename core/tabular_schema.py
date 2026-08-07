"""Pure schema inference shared by tabular and vector data adapters."""

from collections.abc import Iterable
import pandas as pd

from core.coordinates import CoordinateParser


GROUP_CANDIDATES = (
    "sector",
    "species cordylancistrus clade tree",
    "species",
    "especie",
    "codigo",
    "code",
    "drainage",
    "cuenca",
    "site",
    "sitio",
    "country",
    "pais",
)


def coordinate_column_score(columns: Iterable[object]) -> int:
    """Score a column collection by recognized coordinate field names."""

    normalized = tuple(str(column).strip().lower() for column in columns)
    return sum(
        5
        for column in normalized
        if column in CoordinateParser.LAT_CANDIDATES
        or column in CoordinateParser.LON_CANDIDATES
    )


def detect_lat_lon_columns(
    frame: pd.DataFrame,
    lat_col: str | None = None,
    lon_col: str | None = None,
) -> tuple[str, str] | None:
    """Infer latitude and longitude columns without mutating the frame."""

    columns = tuple(str(column).strip() for column in frame.columns)
    column_map = {str(column).strip(): str(column) for column in frame.columns}

    if lat_col and lon_col and lat_col in column_map and lon_col in column_map:
        return column_map[lat_col], column_map[lon_col]

    found_lat = next(
        (
            column_map[column]
            for column in columns
            if column.lower() in CoordinateParser.LAT_CANDIDATES
        ),
        None,
    )
    found_lon = next(
        (
            column_map[column]
            for column in columns
            if column.lower() in CoordinateParser.LON_CANDIDATES
        ),
        None,
    )

    # Some field datasets encode X=latitude/Y=longitude; infer the order by
    # the value ranges used in Colombia and surrounding regions.
    if found_lat is None or found_lon is None:
        x_col = next((column_map[c] for c in columns if c.lower() == "x"), None)
        y_col = next((column_map[c] for c in columns if c.lower() == "y"), None)

        if x_col is not None and y_col is not None:
            x_values = pd.to_numeric(frame[x_col], errors="coerce").dropna()
            y_values = pd.to_numeric(frame[y_col], errors="coerce").dropna()
            if len(x_values) > 0 and len(y_values) > 0:
                if (x_values.min() >= -15 and x_values.max() <= 35) and (
                    y_values.min() <= -30 and y_values.max() >= -120
                ):
                    found_lat, found_lon = x_col, y_col
                elif (y_values.min() >= -15 and y_values.max() <= 35) and (
                    x_values.min() <= -30 and x_values.max() >= -120
                ):
                    found_lat, found_lon = y_col, x_col

    if found_lat is not None and found_lon is not None:
        lat_values = pd.to_numeric(frame[found_lat], errors="coerce").dropna()
        lon_values = pd.to_numeric(frame[found_lon], errors="coerce").dropna()
        if (
            len(lat_values) > 0
            and len(lon_values) > 0
            and lat_values.mean() < -30
            and lon_values.mean() > 0
        ):
            found_lat, found_lon = found_lon, found_lat

    if found_lat is None or found_lon is None:
        return None
    return found_lat, found_lon


def ensure_group_column[FrameT: pd.DataFrame](
    frame: FrameT, user_group_col: str | None = None
) -> tuple[FrameT, str]:
    """Return a frame with a grouping column, copying only when one is added."""

    columns = tuple(str(column).strip() for column in frame.columns)
    column_map = {str(column).strip(): str(column) for column in frame.columns}

    if user_group_col and user_group_col in column_map:
        return frame, column_map[user_group_col]

    candidate = next(
        (
            column_map[column]
            for column in columns
            if column.lower() in GROUP_CANDIDATES
        ),
        None,
    )
    if candidate is not None:
        return frame, candidate

    string_columns = frame.select_dtypes(include=["object", "category"]).columns
    if len(string_columns) > 0:
        return frame, str(string_columns[0])

    normalized = frame.copy()
    normalized["Group"] = "Puntos de Muestreo"
    return normalized, "Group"
