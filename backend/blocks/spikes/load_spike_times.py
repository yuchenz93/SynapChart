
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LoadSpikeTimes(BlockBase):
    """Load spike times for one or more units from a .npy or text file."""

    block_type_id = "load_spike_times"
    display_name = "Load Spike Times"
    category = "Spikes"
    description = "Loads spike times for one or more units from a file."

    inputs: list[PortDefinition] = []
    outputs = [
        PortDefinition("spikes", "NeuroData[spike_times]", "1-D array of spike timestamps (seconds)."),
    ]
    parameters = [
        ParameterDefinition("file_path", "str", "", "Path to spike times file (.npy or .txt)."),
        ParameterDefinition("unit_index", "int", 0, "Unit index to load. Use -1 to concatenate all units."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        path = Path(parameters["file_path"])
        unit_index = int(parameters.get("unit_index", 0))

        if path.suffix == ".npy":
            raw = np.load(str(path), allow_pickle=True)
        else:
            raw = np.loadtxt(str(path))

        # If raw is an object array (array-of-arrays), index into it
        if raw.dtype == object:
            if unit_index == -1:
                spike_times = np.concatenate([raw[i] for i in range(len(raw))])
            else:
                spike_times = np.asarray(raw[unit_index], dtype=float)
        else:
            if raw.ndim == 2:
                spike_times = raw[unit_index] if unit_index != -1 else raw.ravel()
            else:
                spike_times = raw.astype(float)

        spike_times = np.sort(spike_times)
        return {
            "spikes": NeuroData(
                data_type="spike_times",
                array=spike_times,
                metadata={"unit_index": unit_index},
            )
        }
