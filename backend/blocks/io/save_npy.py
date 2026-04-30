
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SaveNpy(BlockBase):
    """Save a NeuroData array to disk as a .npy file."""

    block_type_id = "save_npy"
    display_name = "Save .npy file"
    category = "Data I/O"
    description = "Saves a NeuroData array to disk as .npy."

    inputs = [
        PortDefinition("data", "NeuroData[any]", "Data to save."),
    ]
    outputs: list[PortDefinition] = []
    parameters = [
        ParameterDefinition("file_path", "str", "", "Destination path (e.g. /data/out.npy)."),
        ParameterDefinition("overwrite", "bool", False, "If false, raise an error if the file already exists."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        data: NeuroData = inputs["data"]
        path = Path(parameters["file_path"])
        overwrite = bool(parameters.get("overwrite", False))
        if path.exists() and not overwrite:
            raise FileExistsError(
                f"File already exists: {path}. Set overwrite=True to replace it."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(path), data.array)
        return {}
