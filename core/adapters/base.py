import os
from abc import ABC, abstractmethod

import pandas as pd

from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError
from core.result import Result

# Backwards compatibility alias
SpatialDatasetRepresentation = SpatialDataset


class BaseDataAdapter(ABC):
    """
    Abstract Interface for Data Adapters.
    Adapts external data sources into an immutable SpatialDataset wrapped in a Result monad.
    """

    @abstractmethod
    def can_handle(self, source: DataSource) -> bool:
        """Determines if this adapter can process the given input source."""

    @abstractmethod
    def adapt(
        self,
        source: DataSource,
        lat_col: str | None = None,
        lon_col: str | None = None,
        group_col: str | None = None,
        sheet_name: str | None = None,
        crs: str = "EPSG:4326",
        sep: str | None = None,
    ) -> Result[SpatialDataset, SpatialError]:
        """Transforms input source into Result[SpatialDataset, SpatialError]."""

    @staticmethod
    def derive_dataset_name(source: DataSource) -> str:
        """Helper to derive a clean dataset name from file path or object."""
        if not isinstance(source, pd.DataFrame):
            base = os.path.basename(os.fspath(source))
            name = os.path.splitext(base)[0]
            return name.replace(" ", "_").replace("-", "_")
        return "SpatialDataset"
