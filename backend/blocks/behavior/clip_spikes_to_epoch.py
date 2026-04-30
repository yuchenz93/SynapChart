"""Clip a multi_spike_times NeuroData to a given time window."""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, PortDefinition
from neurodata.types import NeuroData


class ClipSpikesToEpoch(BlockBase):
    """Restrict multi-cell spike times to a time window."""

    block_type_id = "clip_spikes_to_epoch"
    display_name  = "Clip Spikes to Epoch"
    category      = "Behavior"
    description   = (
        "Filters a multi_spike_times NeuroData to keep only spikes within "
        "[t_start, t_end] from a NeuroData[epochs] time_range."
    )

    inputs = [
        PortDefinition("spike_data",  "NeuroData[multi_spike_times]",
                       "All spike times from load_crcns_session."),
        PortDefinition("time_range",  "NeuroData[epochs]",
                       "Time window [t_start, t_end] from select_epoch."),
    ]
    outputs = [
        PortDefinition("spike_data_clipped", "NeuroData[multi_spike_times]",
                       "Spike times restricted to the selected epoch."),
    ]
    parameters = []

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        spikes: NeuroData = inputs["spike_data"]
        tr:     NeuroData = inputs["time_range"]

        arr = np.asarray(tr.array).flatten()
        if len(arr) >= 2:
            t_start, t_end = float(arr[0]), float(arr[1])
        else:
            t_start = float(tr.metadata.get("t_start", arr[0]))
            t_end   = float(tr.metadata.get("t_end",   arr[0]))

        times    = spikes.array
        cell_ids = np.asarray(spikes.metadata.get("spike_cell_ids", []))

        mask = (times >= t_start) & (times <= t_end)

        clipped_times    = times[mask]
        clipped_cell_ids = cell_ids[mask] if len(cell_ids) == len(times) else []

        return {
            "spike_data_clipped": NeuroData(
                data_type = "multi_spike_times",
                array     = clipped_times,
                metadata  = {
                    **spikes.metadata,
                    "spike_cell_ids": (
                        clipped_cell_ids.tolist()
                        if hasattr(clipped_cell_ids, "tolist")
                        else list(clipped_cell_ids)
                    ),
                    "t_start": t_start,
                    "t_end":   t_end,
                },
            )
        }
