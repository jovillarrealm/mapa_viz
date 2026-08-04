import pandas as pd

from core.adapters.base import BaseDataAdapter
from core.adapters.csv_adapter import CSVDataAdapter
from core.adapters.excel_adapter import ExcelDataAdapter
from core.adapters.vector_adapter import VectorDataAdapter
from core.domain import DataSource, SpatialDataset
from core.errors import SpatialError, SpatialErrorCode
from core.result import Err, Ok, Result


class DataAdapterRegistry:
    """
    Central Registry for Data Adapters.
    Automatically matches input sources (files, dataframes, URLs) to the appropriate adapter
    and produces a standardized Result[SpatialDataset, SpatialError].
    """

    def __init__(self):
        self._adapters: list[BaseDataAdapter] = []
        self._register_default_adapters()

    def _register_default_adapters(self):
        self.register(ExcelDataAdapter())
        self.register(CSVDataAdapter())
        self.register(VectorDataAdapter())

    def register(self, adapter: BaseDataAdapter):
        """Registers a new custom adapter at the front of the chain."""
        self._adapters.insert(0, adapter)

    def get_adapter(self, source: DataSource) -> Result[BaseDataAdapter, SpatialError]:
        """Finds the first adapter that can process the source."""
        for adapter in self._adapters:
            if adapter.can_handle(source):
                return Ok(adapter)
        return Err(
            SpatialError(
                code=SpatialErrorCode.UnsupportedFormat,
                message=f"No suitable adapter found for source '{source}'",
                source_path=str(source) if not isinstance(source, pd.DataFrame) else None,
            )
        )

    def load(
        self,
        source: DataSource,
        lat_col: str | None = None,
        lon_col: str | None = None,
        group_col: str | None = None,
        sheet_name: str | None = None,
        crs: str = "EPSG:4326",
        sep: str | None = None,
    ) -> Result[SpatialDataset, SpatialError]:
        """Loads and adapts any supported input source into Result[SpatialDataset, SpatialError]."""
        for adapter in self._adapters:
            if adapter.can_handle(source):
                return adapter.adapt(
                    source,
                    lat_col=lat_col,
                    lon_col=lon_col,
                    group_col=group_col,
                    sheet_name=sheet_name,
                    crs=crs,
                    sep=sep,
                )
        return Err(
            SpatialError(
                code=SpatialErrorCode.UnsupportedFormat,
                message=f"No suitable adapter found for source '{source}'",
                source_path=str(source) if not isinstance(source, pd.DataFrame) else None,
            )
        )


# Global registry instance
registry = DataAdapterRegistry()


def load_dataset(
    source: DataSource,
    lat_col: str | None = None,
    lon_col: str | None = None,
    group_col: str | None = None,
    sheet_name: str | None = None,
    crs: str = "EPSG:4326",
    sep: str | None = None,
) -> Result[SpatialDataset, SpatialError]:
    """Convenience entry point for ingesting any dataset into Result[SpatialDataset, SpatialError]."""
    return registry.load(
        source,
        lat_col=lat_col,
        lon_col=lon_col,
        group_col=group_col,
        sheet_name=sheet_name,
        crs=crs,
        sep=sep,
    )
