"""Convert a NeuroData[states] object to a bounding-box epoch for LFP loading."""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class StatesToEpoch(BlockBase):
    """Return a single [t_start, t_end] epoch spanning all state intervals."""

    block_type_id = "states_to_epoch"
    display_name  = "States to Epoch"
    category      = "maze1d / States"
    description   = (
        "Collapses all time intervals across all states into a single bounding-box "
        "epoch [t_start, t_end].  Feed this into the time_range port of "
        "load_crcns_lfp to avoid loading the full recording."
    )

    inputs = [
        PortDefinition("states", "NeuroData[states]",
                       "Named states from define_maze_states."),
    ]
    outputs = [
        PortDefinition("epoch", "NeuroData[epochs]",
                       "Bounding-box epoch [t_start, t_end] covering all state intervals."),
    ]
    parameters = [
        ParameterDefinition("padding_s", "float", 1.0,
                            "Extra seconds to add before t_start and after t_end "
                            "(ensures full theta cycles at boundaries are captured)."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        states_nd: NeuroData = inputs["states"]
        padding = float(parameters.get("padding_s", 1.0))

        states_dict = states_nd.metadata.get("states", {})

        t_starts = []
        t_ends   = []
        for state in states_dict.values():
            for t0, t1 in state.get("intervals", []):
                t_starts.append(float(t0))
                t_ends.append(float(t1))

        if not t_starts:
            raise ValueError("states_to_epoch: no intervals found in states object.")

        t_start = max(0.0, min(t_starts) - padding)
        t_end   = max(t_ends) + padding

        return {
            "epoch": NeuroData(
                data_type = "epochs",
                array     = np.array([t_start, t_end], dtype=np.float64),
                metadata  = {
                    "t_start":       t_start,
                    "t_end":         t_end,
                    "n_states":      len(states_dict),
                    "padding_s":     padding,
                },
            )
        }
