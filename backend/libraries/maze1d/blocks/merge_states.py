"""Optionally merge multiple states into a new synthetic state.

Useful when an aggregated result must feed further upstream analysis, e.g.
averaging tuning curves across sessions before running a population decoder.
Not needed for terminal visualisation — plot blocks accept all states and let
the user choose which to display via parameters.
"""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class MergeStates(BlockBase):
    """Merge selected states into a new synthetic state (optional)."""

    block_type_id = "merge_states"
    display_name  = "Merge States"
    category      = "maze1d / States"
    description   = (
        "Concatenates time intervals from selected states into a new named state. "
        "Useful when downstream blocks need a cross-session or cross-condition "
        "aggregate.  The merged state inherits direction=None (undirected) unless "
        "all selected states share the same direction, in which case that direction "
        "is preserved."
    )

    inputs = [
        PortDefinition("states", "NeuroData[states]",
                       "Named states from define_maze_states (or another merge_states)."),
    ]
    outputs = [
        PortDefinition("states", "NeuroData[states]",
                       "Original states plus the new merged state."),
    ]
    parameters = [
        ParameterDefinition("state_keys", "str", "",
                            "Comma-separated list of state names to merge, e.g. "
                            "'session1_dir1,session2_dir1'.  Empty = merge all."),
        ParameterDefinition("new_state_name", "str", "merged",
                            "Name for the new synthetic state."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        states_nd = inputs["states"]
        keys_str  = str(parameters.get("state_keys",     "")).strip()
        new_name  = str(parameters.get("new_state_name", "merged")).strip()

        states_dict = dict(states_nd.metadata.get("states", {}))

        if keys_str:
            selected = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            selected = list(states_dict.keys())

        selected = [k for k in selected if k in states_dict]
        if not selected:
            return {"states": states_nd}

        merged_intervals: list[tuple] = []
        directions = set()
        for k in selected:
            merged_intervals.extend(states_dict[k]["intervals"])
            d = states_dict[k].get("direction")
            if d is not None:
                directions.add(d)

        # Sort intervals chronologically
        merged_intervals.sort(key=lambda x: x[0])

        merged_direction = directions.pop() if len(directions) == 1 else None

        states_dict[new_name] = {
            "session_id": "merged",
            "direction":  merged_direction,
            "intervals":  merged_intervals,
            "n_laps":     sum(states_dict[k]["n_laps"] for k in selected),
            "source_keys": selected,
        }

        new_state_keys = list(states_dict.keys())
        n_laps_arr = np.array(
            [states_dict[k]["n_laps"] for k in new_state_keys], dtype=np.float32
        ).reshape(-1, 1)

        return {
            "states": NeuroData(
                data_type     = "states",
                array         = n_laps_arr,
                channel_names = new_state_keys,
                metadata      = {
                    "states":     states_dict,
                    "state_keys": new_state_keys,
                    "n_states":   len(states_dict),
                },
            )
        }
