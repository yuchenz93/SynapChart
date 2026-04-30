
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LoadCsv(BlockBase):
    """Load a CSV file and wrap it in a NeuroData envelope.

    If has_timestamps is True, the first column is treated as timestamps (seconds)
    and excluded from the data array.
    """

    block_type_id = "load_csv"
    display_name = "Load CSV"
    category = "Data I/O"
    description = "Loads a CSV file. First column is treated as timestamps if has_timestamps is true."

    inputs: list[PortDefinition] = []
    outputs = [
        PortDefinition("data", "NeuroData[raw_signal]", "Loaded array"),
    ]
    parameters = [
        ParameterDefinition("file_path", "str", "", "Absolute path to the CSV file."),
        ParameterDefinition("has_timestamps", "bool", True, "If true, first column is timestamps (seconds)."),
        ParameterDefinition("sampling_rate", "float", 1000.0, "Samples per second (used when has_timestamps is false)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        path = Path(parameters["file_path"])
        has_ts = bool(parameters.get("has_timestamps", True))
        sr = float(parameters.get("sampling_rate", 1000.0))

        raw = np.genfromtxt(str(path), delimiter=",")
        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)

        if has_ts and raw.shape[1] > 1:
            timestamps = raw[:, 0]
            arr = raw[:, 1:]
            if arr.shape[1] == 1:
                arr = arr[:, 0]
        else:
            timestamps = None
            arr = raw

        return {
            "data": NeuroData(
                data_type="raw_signal",
                array=arr,
                sampling_rate=sr,
                timestamps=timestamps,
            )
        }
