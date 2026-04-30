
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LoadPosition(BlockBase):
    """Load x/y position and timestamps from a CSV-like file."""

    block_type_id = "load_position"
    display_name = "Load Position"
    category = "Behavior"
    description = "Loads x/y position data and timestamps from file."

    inputs: list[PortDefinition] = []
    outputs = [
        PortDefinition("position", "NeuroData[position]", "2-D position array (N × 2), x and y."),
    ]
    parameters = [
        ParameterDefinition("file_path", "str", "", "Path to position data file (CSV or .npy)."),
        ParameterDefinition("x_col", "int", 0, "Column index for x coordinate."),
        ParameterDefinition("y_col", "int", 1, "Column index for y coordinate."),
        ParameterDefinition("time_col", "int", 2, "Column index for timestamps (seconds)."),
        ParameterDefinition("sampling_rate", "float", 30.0, "Samples per second."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        path = Path(parameters["file_path"])
        x_col = int(parameters.get("x_col", 0))
        y_col = int(parameters.get("y_col", 1))
        time_col = int(parameters.get("time_col", 2))
        sr = float(parameters.get("sampling_rate", 30.0))

        if path.suffix == ".npy":
            raw = np.load(str(path))
        else:
            raw = np.genfromtxt(str(path), delimiter=",")

        xy = np.column_stack([raw[:, x_col], raw[:, y_col]])
        timestamps = raw[:, time_col] if time_col < raw.shape[1] else None

        return {
            "position": NeuroData(
                data_type="position",
                array=xy,
                sampling_rate=sr,
                timestamps=timestamps,
            )
        }
