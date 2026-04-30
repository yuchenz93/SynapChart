
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ExportCsv(BlockBase):
    """Export a NeuroData array to a CSV file."""

    block_type_id = "export_csv"
    display_name = "Export CSV"
    category = "Data I/O"
    description = "Exports a NeuroData array to CSV."

    inputs = [
        PortDefinition("data", "NeuroData[any]", "Data to export."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("file_path", "str", "", "Destination path (e.g. /data/out.csv)."),
        ParameterDefinition("include_timestamps", "bool", True, "If true, prepend the timestamps column."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        data: NeuroData = inputs["data"]
        path = Path(parameters["file_path"])
        include_ts = bool(parameters.get("include_timestamps", True))
        path.parent.mkdir(parents=True, exist_ok=True)

        arr = data.array
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)

        if include_ts and data.timestamps is not None:
            ts_col = data.timestamps.reshape(-1, 1)
            arr = np.hstack([ts_col, arr])

        np.savetxt(str(path), arr, delimiter=",")
        return {}
