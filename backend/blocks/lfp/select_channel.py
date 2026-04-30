"""Select one channel from a multi-channel LFP NeuroData, preserving the lfp type."""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SelectChannel(BlockBase):
    """Select a single channel from a multi-channel LFP signal."""

    block_type_id = "select_channel"
    display_name  = "Select LFP Channel"
    category      = "LFP / EEG"
    description   = (
        "Extracts one channel from a multi-channel NeuroData[lfp] and returns "
        "a 1-D NeuroData[lfp] suitable for bandpass filtering and phase extraction."
    )

    inputs = [
        PortDefinition("lfp", "NeuroData[lfp]",
                       "Multi-channel LFP (n_samples × n_channels)."),
    ]
    outputs = [
        PortDefinition("channel", "NeuroData[lfp]",
                       "Single-channel LFP (n_samples,)."),
    ]
    parameters = [
        ParameterDefinition("channel_index", "int", 0,
                            "Zero-based index of the channel to extract."),
    ]

    def run(self, inputs: dict, parameters: dict[str, Any]) -> dict:
        lfp: NeuroData = inputs["lfp"]
        idx = int(parameters.get("channel_index", 0))

        arr = lfp.array
        if arr.ndim == 1:
            channel = arr
        elif arr.ndim == 2:
            if idx >= arr.shape[1]:
                raise IndexError(
                    f"channel_index {idx} out of range "
                    f"(signal has {arr.shape[1]} channels)."
                )
            channel = arr[:, idx]
        else:
            raise ValueError(f"Expected 1-D or 2-D array, got shape {arr.shape}.")

        ch_name = (
            lfp.channel_names[idx]
            if lfp.channel_names and idx < len(lfp.channel_names)
            else f"ch{idx}"
        )

        return {
            "channel": NeuroData(
                data_type     = "lfp",
                array         = channel,
                sampling_rate = lfp.sampling_rate,
                timestamps    = lfp.timestamps,
                channel_names = [ch_name],
                metadata      = {**lfp.metadata, "channel_index": idx},
            )
        }
