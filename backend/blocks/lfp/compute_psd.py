
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import welch

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class ComputePsd(BlockBase):
    """Compute power spectral density using Welch's method."""

    block_type_id = "compute_psd"
    display_name = "Compute PSD"
    category = "LFP / EEG"
    description = "Computes power spectral density using Welch's method."

    inputs = [
        PortDefinition("signal", "NeuroData[raw_signal]", "Continuous signal."),
    ]
    outputs = [
        PortDefinition("psd", "NeuroData[raw_signal]", "PSD array (power values); frequencies stored in timestamps."),
    ]
    parameters = [
        ParameterDefinition("window_seconds", "float", 1.0, "Welch window length in seconds."),
        ParameterDefinition("overlap", "float", 0.5, "Fractional overlap between windows (0–1)."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        signal: NeuroData = inputs["signal"]
        sr = signal.sampling_rate or 1000.0
        win_sec = float(parameters.get("window_seconds", 1.0))
        overlap = float(parameters.get("overlap", 0.5))

        nperseg = int(win_sec * sr)
        noverlap = int(nperseg * overlap)

        arr = signal.array
        if arr.ndim > 1:
            arr = arr[:, 0]

        freqs, psd_vals = welch(arr, fs=sr, nperseg=nperseg, noverlap=noverlap)

        return {
            "psd": NeuroData(
                data_type="raw_signal",
                array=psd_vals,
                sampling_rate=None,
                timestamps=freqs,   # frequencies stored in timestamps field
                metadata={**signal.metadata, "psd": True, "freq_axis": "timestamps"},
            )
        }
