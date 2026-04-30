
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class SelectReferenceChannel(BlockBase):
    """Select a single channel from a multi-channel signal."""

    block_type_id = "select_reference_channel"
    display_name = "Select Channel"
    category = "LFP / EEG"
    description = "Selects a single channel from a multi-channel signal."

    inputs = [
        PortDefinition("signal", "NeuroData[raw_signal]", "Multi-channel signal (N_samples × N_channels)."),
    ]
    outputs = [
        PortDefinition("channel", "NeuroData[raw_signal]", "Single-channel signal (N_samples,)."),
    ]
    parameters = [
        ParameterDefinition("channel_index", "int", 0, "Zero-based index of the channel to extract."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        idx = int(parameters.get("channel_index", 0))

        arr = signal.array
        if arr.ndim == 1:
            channel = arr
        elif arr.ndim == 2:
            channel = arr[:, idx]
        else:
            raise ValueError(f"Expected 1-D or 2-D array, got shape {arr.shape}.")

        ch_name = (
            signal.channel_names[idx]
            if signal.channel_names and idx < len(signal.channel_names)
            else f"ch{idx}"
        )

        return {
            "channel": NeuroData(
                data_type="raw_signal",
                array=channel,
                sampling_rate=signal.sampling_rate,
                timestamps=signal.timestamps,
                channel_names=[ch_name],
                metadata={**signal.metadata, "channel_index": idx},
            )
        }
