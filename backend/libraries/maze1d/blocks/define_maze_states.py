"""Define named maze states from detected running laps.

Each state is a named collection of time intervals sharing the same
session identity and running direction.  Downstream blocks iterate over
all states automatically, keeping the workflow flat regardless of the
number of sessions or conditions.

Output schema (NeuroData[states], metadata["states"])::

    {
      "<session_id>_dir<direction>": {
        "session_id":  str,
        "direction":   int,          # 1 = descending, 2 = ascending
        "intervals":   [(t0,t1), …], # one per lap
        "n_laps":      int,
      },
      …
    }
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class DefineMazeStates(BlockBase):
    """Group running laps by direction into named states for state-aware analysis."""

    block_type_id = "define_maze_states"
    display_name  = "Define Maze States"
    category      = "maze1d / States"
    description   = (
        "Groups running laps from detect_run_laps by direction and attaches a "
        "session identifier, producing a NeuroData[states] object consumed by "
        "all downstream state-aware maze1d blocks.  Creates one state per "
        "direction that has at least min_laps laps."
    )

    inputs = [
        PortDefinition("laps", "NeuroData[laps]",
                       "Running laps from detect_run_laps."),
    ]
    outputs = [
        PortDefinition("states", "NeuroData[states]",
                       "Named states keyed by '{session_id}_dir{direction}'."),
    ]
    parameters = [
        ParameterDefinition("session_id", "str", "session1",
                            "Unique identifier for this recording session, e.g. 'ec013.527'."),
        ParameterDefinition("min_laps", "int", 3,
                            "Minimum number of laps required to create a state for that direction."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        laps_nd    = inputs["laps"]
        session_id = str(parameters.get("session_id", "session1")).strip()
        min_laps   = int(parameters.get("min_laps", 3))

        lap_list = laps_nd.metadata.get("laps", [])

        states: dict[str, dict] = {}
        for direction in [1, 2]:
            dir_laps = [l for l in lap_list if l["direction"] == direction]
            if len(dir_laps) < min_laps:
                continue
            name = f"{session_id}_dir{direction}"
            states[name] = {
                "session_id": session_id,
                "direction":  direction,
                "intervals":  [(l["t_start"], l["t_end"]) for l in dir_laps],
                "n_laps":     len(dir_laps),
            }

        state_keys = list(states.keys())
        n_laps_arr = np.array(
            [states[k]["n_laps"] for k in state_keys], dtype=np.float32
        ).reshape(-1, 1)

        return {
            "states": NeuroData(
                data_type     = "states",
                array         = n_laps_arr,
                channel_names = state_keys,
                metadata      = {
                    "states":     states,
                    "session_id": session_id,
                    "state_keys": state_keys,
                    "n_states":   len(states),
                },
            )
        }
