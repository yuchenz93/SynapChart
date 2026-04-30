
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import butter, filtfilt

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class BandpassFilter(BlockBase):
    """Zero-phase Butterworth bandpass filter."""

    block_type_id = "bandpass_filter"
    display_name = "Bandpass Filter"
    category = "LFP / EEG"
    description = "Zero-phase Butterworth bandpass filter."

    inputs = [
        PortDefinition("signal", "NeuroData[raw_signal]", "Continuous signal to filter."),
    ]
    outputs = [
        PortDefinition("filtered", "NeuroData[lfp]", "Bandpass-filtered signal."),
    ]
    parameters = [
        ParameterDefinition("low_hz", "float", 4.0, "Lower cutoff frequency (Hz)."),
        ParameterDefinition("high_hz", "float", 12.0, "Upper cutoff frequency (Hz)."),
        ParameterDefinition("order", "int", 4, "Filter order."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        sr = signal.sampling_rate or 1000.0
        low = float(parameters.get("low_hz", 4.0))
        high = float(parameters.get("high_hz", 12.0))
        order = int(parameters.get("order", 4))

        nyq = sr / 2.0
        b, a = butter(order, [low / nyq, high / nyq], btype="band")
        filtered = filtfilt(b, a, signal.array, axis=0)

        return {
            "filtered": NeuroData(
                data_type="lfp",
                array=filtered,
                sampling_rate=sr,
                timestamps=signal.timestamps,
                channel_names=signal.channel_names,
                metadata={**signal.metadata, "low_hz": low, "high_hz": high},
            )
        }
