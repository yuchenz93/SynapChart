
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LoadNpy(BlockBase):
    """Load a .npy or .npz file from disk and wrap it in a NeuroData envelope."""

    block_type_id = "load_npy"
    display_name = "Load .npy file"
    category = "Data I/O"
    description = "Loads a numpy .npy or .npz file from disk."

    inputs: list[PortDefinition] = []
    outputs = [
        PortDefinition("data", "NeuroData[raw_signal]", "Loaded array"),
    ]
    parameters = [
        ParameterDefinition("file_path", "str", "", "Absolute path to the .npy or .npz file."),
        ParameterDefinition("sampling_rate", "float", 1000.0, "Samples per second."),
        ParameterDefinition(
            "data_type_override",
            "enum:raw_signal,lfp,spike_times,position",
            "raw_signal",
            "Override the NeuroData type tag on the loaded array.",
        ),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        path = Path(parameters["file_path"])
        raw = np.load(str(path), allow_pickle=False)
        if isinstance(raw, np.lib.npyio.NpzFile):
            key = list(raw.keys())[0]
            arr = raw[key]
        else:
            arr = raw
        data_type = parameters.get("data_type_override", "raw_signal")
        sr = float(parameters.get("sampling_rate", 1000.0))
        return {"data": NeuroData(data_type=data_type, array=arr, sampling_rate=sr)}
