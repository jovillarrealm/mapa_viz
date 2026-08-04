from dataclasses import dataclass
from enum import Enum, auto


class SpatialErrorCode(Enum):
    FileNotFound = auto()
    MissingCoordinates = auto()
    InvalidCRS = auto()
    TileFetchFailed = auto()
    EmptyDataset = auto()
    ExportFailed = auto()
    UnsupportedFormat = auto()


@dataclass(frozen=True)
class SpatialError:
    """Immutable Domain Error for Spatial Operations."""

    code: SpatialErrorCode
    message: str
    source_path: str | None = None
    details: str | None = None

    def __str__(self) -> str:
        loc = f" at '{self.source_path}'" if self.source_path else ""
        det = f" [{self.details}]" if self.details else ""
        return f"[{self.code.name}]{loc}: {self.message}{det}"
