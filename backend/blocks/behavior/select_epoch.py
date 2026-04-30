"""Extract one named epoch from a sessInfo epochs object.

Outputs a NeuroData[epochs] whose ``array`` is ``[t_start, t_end]`` and whose
metadata carries ``t_start`` / ``t_end`` keys — compatible with the
``time_range`` input port of load_crcns_lfp and clip_spikes_to_epoch.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SelectEpoch(BlockBase):
    """Extract a named epoch time window from sessInfo epoch data."""

    block_type_id = "select_epoch"
    display_name  = "Select Epoch"
    category      = "Behavior"
    description   = (
        "Selects a named epoch (e.g. MazeEpoch, PREEpoch) from CRCNS epoch info "
        "and outputs [t_start, t_end] as a NeuroData[epochs] time window."
    )

    inputs = [
        PortDefinition("epochs_info", "NeuroData[epochs]",
                       "Epoch boundaries from load_crcns_session."),
    ]
    outputs = [
        PortDefinition("time_range", "NeuroData[epochs]",
                       "[t_start, t_end] for the selected epoch."),
    ]
    parameters = [
        ParameterDefinition(
            "epoch_name",
            "enum:MazeEpoch,PREEpoch,POSTEpoch,Wake,NREM,REM,Drowsy,Intermediate",
            "MazeEpoch",
            "Which epoch to extract.",
        ),
        ParameterDefinition(
            "epoch_index", "int", 0,
            "For multi-interval epochs (e.g. Wake has many intervals), "
            "which interval to use. 0 = first.",
        ),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        ei: NeuroData = inputs["epochs_info"]
        epoch_name   = str(parameters.get("epoch_name",   "MazeEpoch"))
        epoch_index  = int(parameters.get("epoch_index",  0))

        meta = ei.metadata
        if epoch_name not in meta:
            raise KeyError(
                f"Epoch '{epoch_name}' not found. "
                f"Available: {list(meta.keys())}"
            )

        val = meta[epoch_name]
        # val is either [t_start, t_end] (single epoch) or [[s0,e0], [s1,e1], ...]
        arr = np.asarray(val, dtype=np.float64)
        if arr.ndim == 1:
            t_start, t_end = float(arr[0]), float(arr[1])
        else:
            # Multi-interval: select by index
            idx = min(epoch_index, len(arr) - 1)
            t_start, t_end = float(arr[idx, 0]), float(arr[idx, 1])

        return {
            "time_range": NeuroData(
                data_type = "epochs",
                array     = np.array([t_start, t_end], dtype=np.float64),
                metadata  = {
                    "epoch_name":  epoch_name,
                    "epoch_index": epoch_index,
                    "t_start":     t_start,
                    "t_end":       t_end,
                },
            )
        }
